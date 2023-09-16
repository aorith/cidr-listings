from typing import Any

import msgspec
from litestar.exceptions import ValidationException
from msgspec import ValidationError


async def run_validation(data: Any, target_type: Any):
    """Run the msgspec validation wrapped in a try/except.

    Validations aren't run automatically by msgpec when
    wrapped into a DTO.

    ValidationError's aren't handled in routes automatically
    when DTOs are involved.
    """
    # Until something like this is implemented: https://github.com/jcrist/msgspec/issues/513
    # but this is better for performance reasons, we only validate incoming data
    try:
        msgspec.msgpack.decode(msgspec.msgpack.encode(data), type=target_type)
    except ValidationError as err:
        raise ValidationException(str(err))  # noqa: B904
