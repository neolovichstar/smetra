"""Small private support screenshots, verified and stripped of image metadata."""
import base64
import io
import re
import warnings

from PIL import Image, ImageOps, UnidentifiedImageError
from backend.business import DomainError


def read(data):
    values = data.get('attachments', [])
    if not isinstance(values, list) or len(values) > 3:
        raise DomainError(400, 'Можно приложить до трёх изображений')
    result = []
    for value in values:
        if not isinstance(value, dict) or not isinstance(value.get('data_url'), str):
            raise DomainError(400, 'Некорректное изображение')
        match = re.fullmatch(r'data:image/(png|jpeg|webp);base64,([A-Za-z0-9+/=]+)', value['data_url'])
        if not match or len(value['data_url']) > 400000:
            raise DomainError(400, 'Изображение слишком большое или имеет неверный формат')
        try:
            raw = base64.b64decode(match[2], validate=True)
            with warnings.catch_warnings():
                warnings.simplefilter('error', Image.DecompressionBombWarning)
                with Image.open(io.BytesIO(raw)) as source:
                    if source.format not in ('JPEG', 'PNG', 'WEBP') or source.width * source.height > 20000000 or getattr(source, 'n_frames', 1) > 1:
                        raise ValueError('invalid image')
                    image = ImageOps.exif_transpose(source).convert('RGB')
                    image.thumbnail((1600, 1600))
                    for quality in (75, 55, 35, 20):
                        buffer = io.BytesIO()
                        image.save(buffer, format='WEBP', quality=quality, method=4)
                        if buffer.tell() <= 220000:
                            break
            encoded = buffer.getvalue()
            if len(encoded) > 220000:
                raise ValueError('too large')
        except (ValueError, OSError, UnidentifiedImageError, Image.DecompressionBombError, Image.DecompressionBombWarning):
            raise DomainError(400, 'Не удалось прочитать изображение. Выберите JPEG, PNG или WebP.') from None
        name = str(value.get('name') or 'Изображение').replace('\\', '/').split('/')[-1][:100]
        result.append({'name': name, 'data_url': 'data:image/webp;base64,' + base64.b64encode(encoded).decode('ascii')})
    return result
