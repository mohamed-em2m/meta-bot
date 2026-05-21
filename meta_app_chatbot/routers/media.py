import os
from fastapi import APIRouter, Query, Response
from fastapi.responses import JSONResponse
from meta_app_chatbot.config.settings import settings

router = APIRouter()

@router.get("/get_audio")
async def get_audio(
    path: str = Query(
        ..., description="Relative path of the audio file in temp folder"
    ),
):
    """
    Returns the audio file located in the ./temp directory.
    """
    try:
        filename = os.path.basename(path)
        ext = filename.split(".")[-1]
        full_path = f"{settings.get('temp_folder')}/{filename}"
        print(f"Full path: {full_path}")
        with open(full_path, "rb") as file:
            attachments = file.read()

        return Response(content=attachments, media_type=f"audio/{ext}")

    except Exception as e:
        print(f"Error fetching attachments: {e}")
        return JSONResponse(status_code=500, content={"error": str(e)})

@router.get("/get_image")
async def get_image(
    path: str = Query(
        ..., description="Relative path of the image file in temp folder"
    ),
):
    """
    Returns the image file located in the temporary directory.
    """
    try:
        filename = os.path.basename(path)
        ext = filename.split(".")[-1].lower()

        if ext not in {"png", "jpg", "jpeg", "gif", "bmp", "webp"}:
            return JSONResponse(
                status_code=400, content={"error": "Unsupported image type"}
            )
        
        temp_dir = settings.get("temp_folder", "./temp")
        full_path = os.path.join(temp_dir, filename)

        with open(full_path, "rb") as file:
            image_data = file.read()

        return Response(content=image_data, media_type=f"image/{ext}")

    except Exception as e:
        print(f"Error fetching attachments: {e}")
        return JSONResponse(status_code=500, content={"error": str(e)})
