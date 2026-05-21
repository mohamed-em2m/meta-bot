import asyncio
import datetime
import json
import logging
import time
import uuid
from typing import Any

import pandas as pd
import tiktoken
from google.cloud import bigquery
from google.cloud.bigquery import (
	ArrayQueryParameter,
	QueryJobConfig,
	ScalarQueryParameter,
)
from langchain.text_splitter import RecursiveCharacterTextSplitter
from vertexai.preview.language_models import TextEmbeddingInput, TextEmbeddingModel

from meta_app_chatbot.agent.utils import log_print
from meta_app_chatbot.config.settings import settings


class BigQueryRAG:
	"""Enhanced BigQuery RAG implementation with vector search capabilities."""

	def __init__(
		self,
		project_id: str = None,
		model_name: str = 'text-multilingual-embedding-002',
	):
		"""Initialize BigQuery client and embedding model."""
		self.client = bigquery.Client(project=project_id)
		self.project_id = project_id or self.client.project
		self.model = TextEmbeddingModel.from_pretrained(model_name)
		self.logger = logging.getLogger(__name__)

		# Initialize tiktoken encoding
		try:
			self.encoding = tiktoken.get_encoding('cl100k_base')
		except Exception as e:
			self.logger.warning(
				f'Failed to load tiktoken encoding: {e}. Using fallback method.'
			)
			self.encoding = None

		# Initialize text splitter
		self.text_splitter = RecursiveCharacterTextSplitter(
			chunk_size=500,
			chunk_overlap=50,
			length_function=lambda x: len(x.split()),
			separators=[
				'\n\n',
				'\n',
				' ',
				'.',
				',',
				'\u200b',  # Zero-width space
				'\uff0c',  # Fullwidth comma
				'\u3001',  # Ideographic comma
				'\uff0e',  # Fullwidth full stop
				'\u3002',  # Ideographic full stop
				'',
			],
		)

	def doc_chunk_embed_insert(
		self,
		dataset_id: str,
		table_id: str,
		doc: str | list[str],
		source: str = '',
		storage: str = '',
		metadata: dict[str, Any] = None,
	):
		"""Process documents, chunk them, and insert with embeddings."""
		if isinstance(doc, str):
			doc = [doc]

		if metadata is None:
			metadata = {}

		base_id = uuid.uuid4().hex + f'_{int(time.time())}'
		docs_chunks = []
		chunk_id = 0

		for item in doc:
			chunks = self.text_splitter.split_text(item)
			for chunk in chunks:
				docs_chunks.append(
					{
						'id': f'{base_id}_{chunk_id}',
						'source': source,
						'chunk_id': str(chunk_id),
						'storage': storage,
						'text': chunk,
						'metadata': metadata,
					}
				)
				chunk_id += 1

		return self.insert_documents(dataset_id, table_id, docs_chunks)

	def get_token_length(self, text: str) -> int:
		"""Get token length of text."""
		if self.encoding:
			return len(self.encoding.encode(text))
		else:
			# Fallback: approximate tokens as words * 1.3
			return int(len(text.split()) * 1.3)

	def run_query(
		self, sql_query: str, use_legacy_sql: bool = False
	) -> bigquery.table.RowIterator:
		"""Execute a SQL query and return results."""
		job_config = QueryJobConfig(use_legacy_sql=use_legacy_sql)
		query_job = self.client.query(sql_query, job_config=job_config)
		return query_job.result()

	def query_to_dataframe(self, sql_query: str) -> pd.DataFrame:
		"""Execute query and return results as pandas DataFrame."""
		query_job = self.client.query(sql_query)
		return query_job.to_dataframe()

	def create_dataset(
		self, dataset_id: str, location: str = 'us-central1'
	) -> bigquery.Dataset | None:
		"""Create a new dataset."""
		dataset_ref = f'{self.project_id}.{dataset_id}'
		dataset = bigquery.Dataset(dataset_ref)
		dataset.location = location

		try:
			dataset = self.client.create_dataset(dataset, exists_ok=True)
			self.logger.info(f'Created dataset {dataset.dataset_id}')
			return dataset
		except Exception as e:
			self.logger.error(f'Dataset creation failed: {e}')
			return None

	def create_documents_table(
		self, dataset_id: str, table_id: str = 'documents'
	) -> bigquery.Table | None:
		"""Create the main documents table with consistent schema."""
		schema = [
			bigquery.SchemaField('id', 'STRING', mode='REQUIRED'),
			bigquery.SchemaField('chunk_id', 'STRING'),
			bigquery.SchemaField('source', 'STRING'),
			bigquery.SchemaField('text', 'STRING', mode='REQUIRED'),
			bigquery.SchemaField('metadata', 'JSON'),
			bigquery.SchemaField('storage', 'STRING'),
			bigquery.SchemaField('embedding', 'FLOAT64', mode='REPEATED'),
			bigquery.SchemaField(
				'created_at',
				'TIMESTAMP',
				default_value_expression='CURRENT_TIMESTAMP()',
			),
		]

		return self._create_table(dataset_id, table_id, schema)

	def _create_table(
		self, schema: dict, dataset_id: str = None, table_id: str = None
	) -> bigquery.Table | None:
		"""Create a new table with specified schema."""
		dataset_id = dataset_id or settings.get('RAG_DB')
		table_id = table_id or settings.get('RAG_TABLE')
		table_ref = f'{self.project_id}.{dataset_id}.{table_id}'
		table = bigquery.Table(table_ref, schema=schema)

		try:
			table = self.client.create_table(table, exists_ok=True)
			self.logger.info(f'Created table {table.table_id}')
			return table
		except Exception as e:
			self.logger.error(f'Table creation failed: {e}')
			return None

	async def get_embedding(
		self,
		text: str | list[str],
		task_type: str = 'RETRIEVAL_DOCUMENT',
		output_dimensionality: int | None = 768,
	) -> list[list[float]]:
		"""Generate embeddings for text input."""
		# Ensure text is a list
		if isinstance(text, str):
			text_list = [text]
		else:
			text_list = text

		# Create embedding inputs
		text_embedding_inputs = [
			TextEmbeddingInput(task_type=task_type, text=item) for item in text_list
		]

		# Prepare kwargs for dimensionality
		kwargs = {}
		if output_dimensionality:
			kwargs['output_dimensionality'] = output_dimensionality

		# Get embeddings
		embeddings = self.model.get_embeddings(text_embedding_inputs, **kwargs)
		return [embedding.values for embedding in embeddings]

	def insert_documents(
		self, dataset_id: str, table_id: str, documents: list[dict[str, Any]]
	) -> bool:
		"""Insert documents with automatic embedding generation.

		Args:
		    documents: List of dicts with keys: id, source, text, metadata (optional)
		"""
		table_ref = f'{self.project_id}.{dataset_id}.{table_id}'

		# Process documents and generate embeddings
		rows_to_insert = []
		for doc in documents:
			try:
				# Generate embedding for the text
				embedding = self.get_embedding(doc['text'])[
					0
				]  # Get first (and only) embedding

				row = {
					'id': doc['id'],
					'source': doc.get('source', ''),
					'chunk_id': doc.get('chunk_id', ''),
					'storage': doc.get('storage', ''),
					'text': doc['text'],
					'metadata': json.dumps(doc.get('metadata', {})),
					'embedding': embedding,
				}
				rows_to_insert.append(row)

			except Exception as e:
				self.logger.error(
					f'Error processing document {doc.get("id", "unknown")}: {e}'
				)
				continue

		# Insert rows
		if rows_to_insert:
			errors = self.client.insert_rows_json(
				table_ref,
				rows_to_insert,
			)
			if errors:
				self.logger.error(f'Insert errors: {errors}')
				return False
			else:
				self.logger.info(
					f'Successfully inserted {len(rows_to_insert)} documents'
				)
				return True
		return False

	async def vector_search(
		self,
		dataset_id: str,
		table_id: str,
		query: str,
		top_k: int = 10,
		distance_metric: str = 'COSINE',
	) -> pd.DataFrame:
		"""Perform vector similarity search."""
		# Generate query embedding
		query_embedding = (
			await self.get_embedding(query, task_type='RETRIEVAL_QUERY')
		)[0]
		return await self._vector_search_by_embedding(
			dataset_id, table_id, query_embedding, top_k, distance_metric
		)

	async def _vector_search_by_embedding(
		self,
		dataset_id: str,
		table_id: str,
		query_embedding: list[float],
		top_k: int = 10,
		distance_metric: str = 'COSINE',
	) -> pd.DataFrame:
		"""Perform vector similarity search using precomputed embeddings."""
		# Validate distance metric
		valid_metrics = ['COSINE', 'EUCLIDEAN', 'DOT_PRODUCT']
		if distance_metric not in valid_metrics:
			raise ValueError(
				f'Invalid distance metric. Must be one of: {valid_metrics}'
			)

		# Build query based on distance metric
		if distance_metric == 'DOT_PRODUCT':
			distance_func = 'ML.DOT_PRODUCT'
			order_direction = 'DESC'  # Higher is better for dot product
		else:
			distance_func = 'ML.DISTANCE'
			order_direction = 'ASC'  # Lower is better for distance metrics

		# Build SQL query with parameterized embedding
		if distance_metric == 'DOT_PRODUCT':
			sql_query = f"""
            SELECT
                id,
                chunk_id,
                source,
                storage,
                text,
                metadata,
                {distance_func}(CAST(embedding AS ARRAY<FLOAT64>),
                               CAST(@query_embedding AS ARRAY<FLOAT64>)) as similarity_score
            FROM `{self.project_id}.{dataset_id}.{table_id}`
            WHERE embedding IS NOT NULL
                AND ARRAY_LENGTH(embedding) > 0
            ORDER BY similarity_score {order_direction}
            LIMIT @top_k
            """
		else:
			sql_query = f"""
            SELECT
                id,
                chunk_id,
                source,
                storage,
                text,
                metadata,
                {distance_func}(CAST(embedding AS ARRAY<FLOAT64>),
                               CAST(@query_embedding AS ARRAY<FLOAT64>), '{distance_metric}') as similarity_score
            FROM `{self.project_id}.{dataset_id}.{table_id}`
            WHERE embedding IS NOT NULL
                AND ARRAY_LENGTH(embedding) > 0
            ORDER BY similarity_score {order_direction}
            LIMIT @top_k
            """

		# Use parameterized queries to prevent injection
		job_config = QueryJobConfig(
			query_parameters=[
				bigquery.ArrayQueryParameter(
					'query_embedding', 'FLOAT64', query_embedding
				),
				bigquery.ScalarQueryParameter('top_k', 'INT64', top_k),
			]
		)

		query_job = self.client.query(sql_query, job_config=job_config)
		return query_job.to_dataframe()

	def hybrid_search(
		self,
		dataset_id: str,
		table_id: str,
		query: str,
		keyword_filter: str | None = None,
		metadata_filters: dict[str, Any] | None = None,
		storage_filter: str | None = None,
		source_filter: str | None = None,
		top_k: int = 10,
	) -> pd.DataFrame:
		"""Perform hybrid search combining vector similarity and metadata filtering."""
		# --- generate embedding ---
		query_embedding = self.get_embedding(query)[0]

		# --- base WHERE + params ---
		where_clauses = [
			'embedding IS NOT NULL',
			'ARRAY_LENGTH(embedding) > 0',
		]
		params = [
			ArrayQueryParameter('query_embedding', 'FLOAT64', query_embedding),
			ScalarQueryParameter('top_k', 'INT64', top_k),
		]

		# --- optional filters ---
		if keyword_filter:
			where_clauses.append('LOWER(text) LIKE @kw')
			params.append(
				ScalarQueryParameter('kw', 'STRING', f'%{keyword_filter.lower()}%')
			)

		if storage_filter:
			where_clauses.append('storage = @storage')
			params.append(ScalarQueryParameter('storage', 'STRING', storage_filter))

		if source_filter:
			where_clauses.append('source = @source')
			params.append(ScalarQueryParameter('source', 'STRING', source_filter))

		if metadata_filters:
			for k, v in metadata_filters.items():
				pname = f'meta_{k}'
				where_clauses.append(
					f"JSON_EXTRACT_SCALAR(metadata, '$.{k}') = @{pname}"
				)
				params.append(ScalarQueryParameter(pname, 'STRING', str(v)))

		where_sql = ' AND '.join(where_clauses)

		# --- build SELECT using schema_dict keys ---
		fields = ', '.join(f'`{f}`' for f in self.schema_dict.keys())

		sql = f"""
        SELECT
          {fields},
          ML.DISTANCE(
            CAST(embedding AS ARRAY<FLOAT64>),
            CAST(@query_embedding AS ARRAY<FLOAT64>),
            'COSINE'
          ) AS similarity_score
        FROM `{self.project_id}.{dataset_id}.{table_id}`
        WHERE {where_sql}
        ORDER BY similarity_score ASC
        LIMIT @top_k
        """

		job_config = QueryJobConfig(query_parameters=params)
		return self.client.query(sql, job_config=job_config).to_dataframe()

	def get_document_chunks(
		self, dataset_id: str, table_id: str, document_id_prefix: str
	) -> pd.DataFrame:
		"""Get all chunks for a specific document, ordered by numeric chunk_id."""
		# build SELECT
		fields = ', '.join(
			f'`{f}`' for f in self.schema_dict.keys() if f not in ('embedding',)
		)
		sql = f"""
        SELECT
          {fields},
          created_at
        FROM `{self.project_id}.{dataset_id}.{table_id}`
        WHERE id LIKE @doc_prefix
        ORDER BY CAST(chunk_id AS INT64)
        """

		job_config = QueryJobConfig(
			query_parameters=[
				ScalarQueryParameter('doc_prefix', 'STRING', f'{document_id_prefix}%')
			]
		)

		return self.client.query(sql, job_config=job_config).to_dataframe()

	def get_table_info(self, dataset_id: str, table_id: str) -> dict[str, Any]:
		"""Get information about a table."""
		table_ref = f'{self.project_id}.{dataset_id}.{table_id}'
		table = self.client.get_table(table_ref)

		return {
			'table_id': table.table_id,
			'num_rows': table.num_rows,
			'num_bytes': table.num_bytes,
			'created': table.created,
			'modified': table.modified,
			'schema': [
				{'name': field.name, 'type': field.field_type, 'mode': field.mode}
				for field in table.schema
			],
		}

	def list_datasets(self) -> list[str]:
		"""List all datasets in the project."""
		datasets = list(self.client.list_datasets())
		return [dataset.dataset_id for dataset in datasets]

	def list_tables(self, dataset_id: str) -> list[str]:
		"""List all tables in a dataset."""
		dataset_ref = f'{self.project_id}.{dataset_id}'
		tables = list(self.client.list_tables(dataset_ref))
		return [table.table_id for table in tables]

	def delete_table(
		self, dataset_id: str, table_id: str, not_found_ok: bool = True
	) -> None:
		"""Delete a table."""
		table_ref = f'{self.project_id}.{dataset_id}.{table_id}'
		self.client.delete_table(table_ref, not_found_ok=not_found_ok)
		self.logger.info(f'Deleted table {table_ref}')

	def delete_documents_by_source(
		self, dataset_id: str, table_id: str, source: str
	) -> int:
		"""Delete all documents from a specific source."""
		sql_query = f"""
        DELETE FROM `{self.project_id}.{dataset_id}.{table_id}`
        WHERE source = @source
        """

		job_config = QueryJobConfig(
			query_parameters=[bigquery.ScalarQueryParameter('source', 'STRING', source)]
		)

		query_job = self.client.query(sql_query, job_config=job_config)
		query_job.result()

		# Get number of affected rows
		num_deleted = query_job.num_dml_affected_rows or 0
		self.logger.info(f'Deleted {num_deleted} documents from source: {source}')
		return num_deleted


class UnifiedBigQueryRAG(BigQueryRAG):
	def __init__(self, *args, columns_dict: dict[str, dict[str, Any]] = None, **kwargs):
		super().__init__(*args, **kwargs)
		if columns_dict:
			self.schema_dict = columns_dict
			self.bq_schema = self.create_schema(columns_dict)

	def create_documents_table(
		self, dataset_id: str, table_id: str = 'documents', schema: dict = {}
	) -> bigquery.Table | None:
		"""Create the main documents table with consistent schema."""
		schema_dict = schema or self.schema
		if not schema_dict:
			raise ValueError('Schema dict is required')
		schema = self.create_schema(schema_dict)

		return self._create_table(schema, dataset_id, table_id)

	@staticmethod
	def create_schema(
		columns_dict: dict[str, dict[str, Any]],
	) -> list[bigquery.SchemaField]:
		return [
			bigquery.SchemaField(
				name, props['type'], **{k: v for k, v in props.items() if k != 'type'}
			)
			for name, props in columns_dict.items()
		]

	def doc_chunk_embed_insert(
		self,
		dataset_id: str,
		table_id: str,
		doc: dict[str, Any] or list[dict[str, Any]],
		schema_dict: dict[str, dict[str, Any]] = None,
		split: bool = False,
		main_column: str = 'text',
	) -> bool:
		schema_dict = schema_dict or self.schema_dict
		if not schema_dict:
			raise ValueError('Schema dict is required')
		if isinstance(doc, dict):
			doc = [doc]

		base_id = uuid.uuid4().hex + f'_{int(time.time())}'
		docs_chunks = []
		chunk_id = 0

		for item in doc:
			text = item[main_column]
			chunks = self.text_splitter.split_text(text) if split else [text]
			for chunk in chunks:
				chunk_data = {'id': f'{base_id}_{chunk_id}', main_column: chunk}
				# carry over other metadata fields
				for fld in schema_dict:
					if fld not in ('id', main_column, 'embedding', 'created_at'):
						chunk_data[fld] = item.get(fld)
				docs_chunks.append(chunk_data)
				chunk_id += 1

		return self.insert_documents(
			dataset_id, table_id, docs_chunks, schema_dict, main_column
		)

	def check_row_to_schema(
		self, row: dict[str, Any], schema_dict: dict[str, dict[str, Any]]
	) -> dict[str, Any]:
		row_dict = {}
		# validate required
		for fld, props in schema_dict.items():
			if props.get('mode') == 'REQUIRED' and fld not in row:
				raise ValueError(f'Missing required field {fld}')

		for fld, val in row.items():
			if fld not in schema_dict:
				continue
			fld_type = schema_dict[fld]['type']
			if fld_type == 'STRING':
				row_dict[fld] = str(val)
			elif fld_type == 'JSON':
				row_dict[fld] = json.dumps(val)
			elif fld_type == 'FLOAT64':
				row_dict[fld] = (
					[float(x) for x in val] if isinstance(val, list) else float(val)
				)
			elif fld_type == 'TIMESTAMP':
				row_dict[fld] = (
					val.isoformat() if isinstance(val, datetime.datetime) else str(val)
				)
			elif fld_type == 'INTEGER':
				row_dict[fld] = int(val)
			elif fld_type == 'BOOLEAN':
				row_dict[fld] = bool(val)
			else:
				row_dict[fld] = val
		return row_dict

	def insert_documents(
		self,
		dataset_id: str,
		table_id: str,
		documents: list[dict[str, Any]],
		schema_dict: dict[str, dict[str, Any]],
		main_column: str = 'text',
	) -> bool:
		table_ref = f'{self.project_id}.{dataset_id}.{table_id}'
		rows_to_insert = []
		for item in documents:
			try:
				validated = self.check_row_to_schema(item, schema_dict)
				embedding = asyncio.run(self.get_embedding(validated[main_column]))[0]
				row = {key: value for key, value in validated.items()}
				row['embedding'] = embedding
				rows_to_insert.append(row)
			except Exception as e:
				self.logger.error(f'Error processing {item.get("id")}: {e}')
		if not rows_to_insert:
			return False

		errors = self.client.insert_rows_json(table_ref, rows_to_insert)
		if errors:
			self.logger.error(f'Insert errors: {errors}')
			return False
		self.logger.info(f'Inserted {len(rows_to_insert)} rows')
		return True

	async def vector_search(
		self,
		dataset_id: str,
		table_id: str,
		query: str,
		top_k: int = 10,
		distance_metric: str = 'COSINE',
		schema_dict: dict[str, dict[str, Any]] = None,
	) -> pd.DataFrame:
		schema_dict = schema_dict or self.schema_dict
		if not schema_dict:
			raise ValueError('Schema dict required')

		q_emb = (await self.get_embedding(query, task_type='RETRIEVAL_QUERY'))[0]
		return await self._vector_search_by_embedding(
			dataset_id, table_id, q_emb, top_k, distance_metric, schema_dict
		)

	async def _vector_search_by_embedding(
		self,
		dataset_id: str,
		table_id: str,
		query_embedding: list[float],
		top_k: int,
		distance_metric: str,
		schema_dict: dict[str, dict[str, Any]],
	) -> pd.DataFrame:
		valid_metrics = {
			'COSINE': ('ML.DISTANCE', 'ASC'),
			'EUCLIDEAN': ('ML.DISTANCE', 'ASC'),
			'DOT_PRODUCT': ('ML.DOT_PRODUCT', 'DESC'),
		}
		if distance_metric not in valid_metrics:
			raise ValueError(f'Invalid metric: choose from {list(valid_metrics)}')
		dist_func, order_dir = valid_metrics[distance_metric]

		fields = [f'`{fld}`' for fld in schema_dict]
		fields_sql = ', '.join(fields)

		# build query
		params = [
			bigquery.ArrayQueryParameter('query_embedding', 'FLOAT64', query_embedding),
			bigquery.ScalarQueryParameter('top_k', 'INT64', top_k),
		]
		job_config = QueryJobConfig(query_parameters=params)

		if distance_metric == 'DOT_PRODUCT':
			metric_sql = f'{dist_func}(CAST(embedding AS ARRAY<FLOAT64>), CAST(@query_embedding AS ARRAY<FLOAT64>))'
		else:
			metric_sql = f"{dist_func}(CAST(embedding AS ARRAY<FLOAT64>), CAST(@query_embedding AS ARRAY<FLOAT64>), '{distance_metric}')"

		sql = f"""
        SELECT {fields_sql}, {metric_sql} AS similarity_score
        FROM `{self.project_id}.{dataset_id}.{table_id}`
        WHERE embedding IS NOT NULL AND ARRAY_LENGTH(embedding) > 0
        ORDER BY similarity_score {order_dir}
        LIMIT @top_k
        """
		log_print('info', 'start retrive from bigquery')
		df = self.client.query(sql, job_config=job_config).to_dataframe()
		log_print('info', 'end retrive from bigquery')

		return df

	def hybrid_search(
		self,
		dataset_id: str,
		table_id: str,
		query: str,
		keyword_filter: str | None = None,
		metadata_filters: dict[str, Any] | None = None,
		storage_filter: str | None = None,
		source_filter: str | None = None,
		top_k: int = 10,
	) -> pd.DataFrame:
		"""Perform hybrid search combining vector similarity and metadata filtering."""
		# --- generate embedding ---
		query_embedding = self.get_embedding(query)[0]

		# --- base WHERE + params ---
		where_clauses = [
			'embedding IS NOT NULL',
			'ARRAY_LENGTH(embedding) > 0',
		]
		params = [
			ArrayQueryParameter('query_embedding', 'FLOAT64', query_embedding),
			ScalarQueryParameter('top_k', 'INT64', top_k),
		]

		# --- optional filters ---
		if keyword_filter:
			where_clauses.append('LOWER(text) LIKE @kw')
			params.append(
				ScalarQueryParameter('kw', 'STRING', f'%{keyword_filter.lower()}%')
			)

		if storage_filter:
			where_clauses.append('storage = @storage')
			params.append(ScalarQueryParameter('storage', 'STRING', storage_filter))

		if source_filter:
			where_clauses.append('source = @source')
			params.append(ScalarQueryParameter('source', 'STRING', source_filter))

		if metadata_filters:
			for k, v in metadata_filters.items():
				pname = f'meta_{k}'
				where_clauses.append(
					f"JSON_EXTRACT_SCALAR(metadata, '$.{k}') = @{pname}"
				)
				params.append(ScalarQueryParameter(pname, 'STRING', str(v)))

		where_sql = ' AND '.join(where_clauses)

		# --- build SELECT using schema_dict keys ---
		fields = ', '.join(f'`{f}`' for f in self.schema_dict.keys())

		sql = f"""
        SELECT
          {fields},
          ML.DISTANCE(
            CAST(embedding AS ARRAY<FLOAT64>),
            CAST(@query_embedding AS ARRAY<FLOAT64>),
            'COSINE'
          ) AS similarity_score
        FROM `{self.project_id}.{dataset_id}.{table_id}`
        WHERE {where_sql}
        ORDER BY similarity_score ASC
        LIMIT @top_k
        """

		job_config = QueryJobConfig(query_parameters=params)
		return self.client.query(sql, job_config=job_config).to_dataframe()

	def get_document_chunks(
		self, dataset_id: str, table_id: str, document_id_prefix: str
	) -> pd.DataFrame:
		"""Get all chunks for a specific document, ordered by numeric chunk_id."""
		# build SELECT
		fields = ', '.join(
			f'`{f}`' for f in self.schema_dict.keys() if f not in ('embedding',)
		)
		sql = f"""
        SELECT
          {fields},
          created_at
        FROM `{self.project_id}.{dataset_id}.{table_id}`
        WHERE id LIKE @doc_prefix
        ORDER BY CAST(chunk_id AS INT64)
        """

		job_config = QueryJobConfig(
			query_parameters=[
				ScalarQueryParameter('doc_prefix', 'STRING', f'{document_id_prefix}%')
			]
		)

		return self.client.query(sql, job_config=job_config).to_dataframe()


def export_to_bigquery(bigquery_db, shots, schema):
	for shot in shots:
		shot_key = 'Shot' if 'Shot' in shot else 'shot'
		few_shot = '\n'.join([f'{item[0]}:' + item[1] for item in shot[shot_key]])
		scenario = shot['scenario']
		for message in shot[shot_key]:
			role = message[0]
			content = message[1]
			if role == 'user':
				title = f'{scenario}\n{content}'
				doc = {'text': title, 'shot': few_shot, 'metadata': {}}
				bigquery_db.doc_chunk_embed_insert(
					'RealEstateInfo2', settings.get('FEW_SHOTS_TABLE'), doc, schema
				)
