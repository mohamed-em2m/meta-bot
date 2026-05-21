import wave

from pydub import AudioSegment


def save_audio_as_wave(filename, pcm, channels=1, rate=24000, sample_width=2):
	with wave.open(filename, 'wb') as wf:
		wf.setnchannels(channels)
		wf.setsampwidth(sample_width)
		wf.setframerate(rate)
		wf.writeframes(pcm)


def save_audio(
	filename, pcm_data, format, channels=1, rate=24000, sample_width=2, **kwargs
):
	"""
	Save PCM data to MP3, MP4, OGG, etc.
	output_format: "mp3", "aac", "ogg", etc.
	"""
	# Create an AudioSegment from raw PCM
	audio = AudioSegment(
		data=pcm_data, sample_width=sample_width, frame_rate=rate, channels=channels
	)

	output_file = filename
	audio.export(output_file, format=format)
	print(f'[✓] {format.upper()} saved to {output_file}')
