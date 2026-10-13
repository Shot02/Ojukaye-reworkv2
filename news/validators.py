from django.core.exceptions import ValidationError
import os


MAX_VIDEO_SIZE_MB = 100
ALLOWED_VIDEO_EXTENSIONS = ['.mp4', '.webm', '.mov', '.m4v']


def validate_video_file(file):
    """
    Two checks:
      1. Size — reject files over MAX_VIDEO_SIZE_MB
      2. Extension — reject anything that isn't a known video format
    """
    # Size
    if file.size > MAX_VIDEO_SIZE_MB * 1024 * 1024:
        raise ValidationError(
            f'Video is too large. Max size is {MAX_VIDEO_SIZE_MB}MB '
            f'(yours is {file.size / 1024 / 1024:.1f}MB).'
        )

    # Extension
    ext = os.path.splitext(file.name)[1].lower()
    if ext not in ALLOWED_VIDEO_EXTENSIONS:
        raise ValidationError(
            f'Unsupported video format "{ext}". '
            f'Allowed: {", ".join(ALLOWED_VIDEO_EXTENSIONS)}.'
        )

    return file