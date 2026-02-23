from __future__ import annotations

from django.core.exceptions import ValidationError
from django.utils.translation import gettext_lazy as _

MAX_IMAGE_SIZE_MB = 1


def validate_image_file_size(image) -> None:
    """Garante que o arquivo de imagem não ultrapasse o limite configurado."""
    if not image:
        return

    limit_bytes = MAX_IMAGE_SIZE_MB * 1024 * 1024
    if image.size > limit_bytes:
        raise ValidationError(
            _("A imagem deve ter no máximo %(limit)d MB."),
            params={"limit": MAX_IMAGE_SIZE_MB},
        )
