from datetime import datetime

import httpx

from filehub.colors import BRIGHT_YELLOW, RESET


class BranchNotFoundError(Exception):
    """Raised when the user specified branch does not exist."""

    def __init__(self, branch: str, repository: str) -> None:
        self.branch = branch
        self.repository = repository
        message = (
            f"'{self.branch}' Branch does not exist on '{self.repository}' repository."
        )

        super().__init__(message)


def handle_client_error(error: httpx.HTTPError) -> None:
    if isinstance(error, httpx.ConnectError):
        print(
            "\nFailed to establish connection, try:\n- Checking yout network connection."
        )

    if isinstance(error, httpx.HTTPStatusError):
        status_code = error.response.status_code

        if status_code == 401:
            print(
                "\n Bad Credentials for authentication, please check your username or password (or access token)!"
            )
        elif status_code == 403:
            headers = error.response.headers
            rate_limit_reset = int(headers["x-ratelimit-reset"])
            reset_time = datetime.fromtimestamp(rate_limit_reset)
            print(
                f"You have exhausted the Github API rate limit.\nTry again in {BRIGHT_YELLOW}{reset_time}{RESET}"
            )
        else:
            error_msg = f"{str(error)}"
            if status_code == 404:
                error_msg += ", please check the input URL!"
            print(error_msg)
    else:
        print(f"Error: {str(error)}")
