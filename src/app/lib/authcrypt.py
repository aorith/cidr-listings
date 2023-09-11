from hashlib import blake2b
from os import urandom

from argon2 import PasswordHasher
from argon2.exceptions import VerificationError, VerifyMismatchError

ph = PasswordHasher()


async def generate_salt_and_hashed_password(plain_password: str) -> tuple[str, str]:
    """Generates a new salt and a hashed_password.

    A new salt is always generated when calling this function, that
    salt is used to generate the hash of the provided plain_password.

    :param plain_password: Plain password
    :returns: (salt, hashed_password)
    """
    # generate the salt
    b2 = blake2b(urandom(60))
    salt = b2.hexdigest()

    # append salt to the plain password and generate the final hash
    hash = ph.hash(plain_password + salt)
    return salt, hash


async def verify_password(salt: str, hashed_password: str, plain_password: str) -> bool:
    """Verifies the plain password against the hashed one."""
    try:
        return ph.verify(hashed_password, plain_password + salt)
    except VerifyMismatchError:
        # Secret does not match the password
        return False
    except VerificationError:
        # Verification failed
        raise
    except Exception as err:
        print(err)
        raise
