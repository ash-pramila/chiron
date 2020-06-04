from datetime import datetime, timedelta
from typing import Text

from fastapi import Depends, HTTPException, status, Request
from jwt import PyJWTError, decode, encode

from bot_trainer.utils import Utility
from .models import User, TokenData
from .processor import AccountProcessor

Utility.load_evironment()


class Authentication:
    """ This class defines functions that are necessary for the authentication processes of
        the bot trainer """
    SECRET_KEY = Utility.environment["SECRET_KEY"]
    ALGORITHM = Utility.environment["ALGORITHM"]
    ACCESS_TOKEN_EXPIRE_MINUTES = Utility.environment["ACCESS_TOKEN_EXPIRE_MINUTES"]

    async def get_current_user(
        self, request: Request, token: str = Depends(Utility.oauth2_scheme)
    ):
        """ Validates the user credentials and facilitates the login process """
        credentials_exception = HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Could not validate credentials",
            headers={"WWW-Authenticate": "Bearer"},
        )
        try:
            payload = decode(token, self.SECRET_KEY, algorithms=[self.ALGORITHM])
            username: str = payload.get("sub")
            if username is None:
                raise credentials_exception
            token_data = TokenData(username=username)
        except PyJWTError:
            raise credentials_exception
        user = AccountProcessor.get_user_details(token_data.username)
        if user is None:
            raise credentials_exception

        user_model = User(**user)
        if user["is_integration_user"]:
            alias_user = request.headers.get("X-USER")
            if Utility.check_empty_string(alias_user):
                raise HTTPException(
                    status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                    detail="Alias user missing for integration",
                    headers={"WWW-Authenticate": "Bearer"},
                )
            user_model.alias_user = alias_user
        return user_model

    def __create_access_token(self, *, data: dict, is_integration=False):
        """ Creates access tokens (JSON Web Tokens) for secure login """
        expires_delta = timedelta(minutes=self.ACCESS_TOKEN_EXPIRE_MINUTES)
        to_encode = data.copy()
        if not is_integration:
            if expires_delta:
                expire = datetime.utcnow() + expires_delta
            else:
                expire = datetime.utcnow() + timedelta(minutes=15)
            to_encode.update({"exp": expire})
        encoded_jwt = encode(to_encode, self.SECRET_KEY, algorithm=self.ALGORITHM)
        return encoded_jwt

    def __authenticate_user(self, username: str, password: str):
        """ Checks if the user name and password match. It returns the user details
            if they match and returns False if not """
        user = AccountProcessor.get_user_details(username)
        if not user:
            return False
        if not Utility.verify_password(password, user["password"]):
            return False
        return user

    def authenticate(self, username: Text, password: Text):
        """ Generates an access token if the user name and password match """
        user = self.__authenticate_user(username, password)
        if not user:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Incorrect username or password",
                headers={"WWW-Authenticate": "Bearer"},
            )
        access_token = self.__create_access_token(data={"sub": user["email"]})
        return access_token

    def generate_integration_token(self, bot: Text, account: int):
        """ Generates an access token for secure integration of the bot
            with an external service/architecture """
        integration_user = AccountProcessor.get_integration_user(bot, account)
        access_token = self.__create_access_token(
            data={"sub": integration_user["email"]}, is_integration=True
        )
        return access_token
