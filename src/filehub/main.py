import argparse
import asyncio
import subprocess
import sys
import time
from datetime import datetime
from pathlib import Path
from subprocess import CalledProcessError
from urllib.parse import urlsplit

import aiofiles
import httpx
from rich.progress import (
    BarColumn,
    DownloadColumn,
    Progress,
    SpinnerColumn,
    TaskID,
    TextColumn,
    TimeElapsedColumn,
    TimeRemainingColumn,
    TransferSpeedColumn,
)
from filehub.errors import BranchNotFoundError

# terminal colors
RESET = "\033[0m"  # called to return to standard terminal text color
BRIGHT_RED = "\033[91m"
BRIGHT_GREEN = "\033[92m"
BRIGHT_YELLOW = "\033[93m"
WHITE = "\033[97m"

# download dir
DOWNLOAD_DIR = Path("Filehub")

# limit download to only 4 cpus
DOWNLOAD_LIMIT = 4

# flags
BRANCH = False
FLATTEN = False
DIR = False
ZIP = False

fetch_progress = Progress(
    TimeElapsedColumn(),
    TextColumn("[bold green]{task.description}"),
    SpinnerColumn("dots"),
)

download_progress = Progress(
    TextColumn("[bold blue]{task.fields[filename]}", justify="right"),
    BarColumn(bar_width=None),
    "[progress.percentage]{task.percentage:>3.1f}%",
    "•",
    DownloadColumn(),
    "•",
    TransferSpeedColumn(),
    "•",
    TimeRemainingColumn(),
)


def get_arguments() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="A simple CLI program to download specific files from Github repositories."
    )

    # positional argument
    parser.add_argument(
        "url",
        type=str,
        metavar="URL",
        help="Required Github repository URL to download from.",
    )

    # optional arguments
    parser.add_argument("-p", "--path", help="Download path of the file.")
    parser.add_argument(
        "-b",
        "--branch",
        nargs="?",
        default=None,
        metavar="BRANCH",
        help="Branch of the repository to download from.",
    )
    parser.add_argument(
        "-f",
        "--flatten",
        action="store_true",
        help="Flatten directory structure.",
    )
    parser.add_argument(
        "-z",
        "--zip",
        action="store_true",
        help="Download zip archive of a repository.",
    )
    parser.add_argument(
        "-r",
        "--rate-limit",
        action="store_true",
        help="Check Github API rate limit uses.",
    )
    parser.add_argument(
        "-d", "--dir", action="store_true", help="Download complete directory."
    )

    args = parser.parse_args()
    return args


def timing(start, fetch, download, finish):
    fetch_time = fetch - start
    select_time = download - fetch
    download_time = finish - download
    total_time = finish - start

    print(
        f"\nFetched files in: {BRIGHT_RED}{fetch_time:.2f}{RESET} seconds. {(fetch_time / total_time) * 100:.2f}% of total time.",
    )
    print(
        f"Selected files in: {BRIGHT_RED}{select_time:.2f}{RESET} seconds. {(select_time / total_time) * 100:.2f}% of total time.",
    )
    print(
        f"Downloaded files in: {BRIGHT_RED}{download_time:.2f}{RESET} seconds. {(download_time / total_time) * 100:.2f}% of total time.",
    )
    print(
        f"Total execution time: {BRIGHT_RED}{total_time:.2f}{RESET} seconds. {(total_time / total_time) * 100:.2f}% of total time.",
    )


def validate_url(url: str):
    """Verify if the provided url is Github url or not."""
    segments = urlsplit(url)

    if segments.netloc not in ("github.com", "gist.github.com"):
        raise ValueError(f"{url} is not a valid Github URL!")

    if segments.scheme not in ("https", "http"):
        raise ValueError("URL must start with http:// or https://")


def validate_branch(owner: str, repo: str, branch: str) -> bool:
    # verify the existence of the branch if provided as an argument.
    branch_url = f"https://api.github.com/repos/{owner}/{repo}/branches/{branch}"

    res = httpx.get(branch_url)
    if res.status_code != 200:
        return False

    return True


def check_user_rate_limit() -> None:
    response = httpx.get("https://api.github.com/rate_limit").json()
    rate_remaining = response["rate"]["remaining"]
    rate_used = response["rate"]["used"]
    reset_time = datetime.fromtimestamp(response["rate"]["reset"])

    print(
        f"\n{BRIGHT_YELLOW}[!]{RESET} Github API Remaining Rates: {BRIGHT_YELLOW}{rate_remaining}{RESET}"
    )
    print(
        f"{BRIGHT_YELLOW}[!]{RESET} Github API Used Rates: {BRIGHT_YELLOW}{rate_used}{RESET}"
    )
    print(f"{BRIGHT_YELLOW}[!]{RESET} Reset: {BRIGHT_YELLOW}{str(reset_time)}{RESET}")


def handle_client_error(error: httpx.HTTPError) -> None:
    if isinstance(error, httpx.ConnectError):
        print(
            "\nFailed to establish connection, try:\n- Checking your network connection."
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
            error_msg = f"\n{str(error)}"
            if status_code == 404:
                error_msg += "or try checking the provided URL!"
            print(error_msg)
    else:
        print(f"\nError: {str(error)}")


def parse_repo_url(cmd_args: argparse.Namespace) -> dict:
    info = {}

    # verify github url
    validate_url(cmd_args.url)

    url = urlsplit(cmd_args.url)
    path = url.path.strip("/").split("/")
    path_segments = [item for item in path if item.strip()]

    if len(path_segments) < 2:
        match url.netloc:
            case "github.com":
                raise ValueError(
                    "Invalid URL: https://github.com/owner/repository is expected."
                )
            case "gist.github.com":
                raise ValueError(
                    "Invalid URL: https://gist.github.com/owner/gistid is expected."
                )

    info["owner"] = path_segments[0]
    info["repository"] = path_segments[1]
    info["branch"] = None
    info["path"] = None

    # if url already consists the branch or has `blob` in it
    # and user provides a different branch
    # as an argument then ignore the branch flag
    global BRANCH
    if "tree" in path_segments or "blob" in path_segments and BRANCH:
        BRANCH = False

    # if branch is provided as an argument
    if BRANCH:
        # verify the existence of user provided branch
        if not validate_branch(info["owner"], info["repository"], cmd_args.branch):
            raise BranchNotFoundError(cmd_args.branch, info["repository"])

        info["branch"] = cmd_args.branch
    else:
        # find branch in url
        if len(path_segments) > 2:
            if ("blob" not in path_segments) ^ ("tree" not in path_segments):
                # NOTE: IN SOME CASES BRANCH NAME MAY LOOK LIKE PATH SUCH AS feat/something
                # SO TO IDENTIFY RIGHT BRANCH, CONSTRUCT AND VALIDATE BRANCH BY ITERATING
                # OVER PATH
                for i in range(1, len(path_segments)):
                    branch_name = "/".join(path_segments[3:][:i])
                    if validate_branch(info["owner"], info["repository"], branch_name):
                        info["branch"] = branch_name
                        # rest of the path after branch
                        info["path"] = "/".join(path_segments[3:][i:])
                        break
            else:
                raise ValueError(f"Invalid URL: {cmd_args.url} is not a valid URL.")
    # print(info)
    return info


def process_request_url(
    owner: str, repo: str, branch: str | None, path: str | None
) -> str:
    if ZIP:
        zip_prefix = f"https://api.github.com/repos/{owner}/{repo}/zipball"
        zip_suffix = ""
        if branch:
            zip_suffix = f"/{branch}"
        return zip_prefix + zip_suffix

    repo_url_prefix = f"https://api.github.com/repos/{owner}/{repo}/contents"
    repo_url_suffix = ""

    if branch and path:
        repo_url_suffix = f"/{path}?ref={branch}"
    elif branch:
        repo_url_suffix = f"?ref={branch}"
    elif path:
        repo_url_suffix = f"/{path}"

    return repo_url_prefix + repo_url_suffix


async def get_repository_content(repo_info: dict) -> list[dict]:
    # print("Fetching repository contents...\n")

    request_url = process_request_url(
        repo_info["owner"],
        repo_info["repository"],
        repo_info["branch"],
        repo_info["path"],
    )
    fetched_urls = [request_url]

    response = []
    files = []

    try:
        fetch_start_time = time.perf_counter()
        with fetch_progress:
            fetch_task = fetch_progress.add_task(
                description="Fetching repository content"
            )
            async with httpx.AsyncClient() as client:
                for req in fetched_urls:
                    # print(
                    #     BRIGHT_GREEN + f"[{i + 1}]" + RESET + " Fetched URL: ", end=""
                    # )
                    # print(BRIGHT_YELLOW + req + RESET)
                    # fetch_progress.console.log(f"Fetched URL: [bold yellow]{req}")

                    res = await client.get(req)
                    res.raise_for_status()

                    # response is a dict if it's single file
                    # else it is a list of dicts of multiple files
                    if isinstance(res.json(), dict):
                        response.append(res.json())
                    else:
                        response = res.json()
                    # print(f"{BRIGHT_GREEN} {response} {RESET}")

                    if response:
                        # sort files and directories
                        for res in response:
                            # print(f"{BRIGHT_YELLOW} {res} {RESET}")
                            if res["type"] == "file":
                                # remove the filename from the path
                                res["path"] = "/".join(res["path"].split("/")[:-1])
                                files.append(res)
                            else:
                                fetched_urls.append(res["url"])

                    response.clear()

            fetch_progress.update(fetch_task, visible=False)

        fetch_finish_time = time.perf_counter()
        print(
            f"Fetched {BRIGHT_GREEN}{len(files)}{RESET} files in {fetch_finish_time - fetch_start_time:.2f}s."
        )
    except httpx.HTTPError as exc:
        handle_client_error(exc)
        sys.exit(1)

    return files


def select_files(files: list[dict] | None = None) -> list[dict] | None:
    if not files:
        return

    if len(files) < 2 or DIR:
        return files

    # get aall the file names
    file_names = [file["name"] for file in files]
    file_input = "\n".join(file_names)

    try:
        result = subprocess.run(
            [
                "fzf",
                "-m",
                "--border-label",
                "Select Files 📂",
                "--height",
                "~50%",
                "--layout",
                "reverse",
                "--border",
                "--padding",
                "1,2",
                "--header",
                "TAB: mark | ENTER: confirm",
                "--input-label",
                "Input",
                "--exit-0",
            ],
            capture_output=True,
            text=True,
            check=True,
            input=file_input,
        )
    except CalledProcessError:
        print("No file selected, Aborting!")
        raise

    selected_files = result.stdout.split("\n")[:-1]
    selected = []

    # print(f"{BRIGHT_GREEN}[+]{RESET} SELECTED FILES:\n")

    for idx, file in enumerate(files):
        if file["name"] in selected_files:
            # print(f"\t{BRIGHT_GREEN}[{idx}]{RESET} {file['name']}")
            selected.append(file)
    print()

    return selected


def download_zip(repo_info: dict) -> None:
    url = process_request_url(
        repo_info["owner"],
        repo_info["repository"],
        repo_info["branch"],
        repo_info["path"],
    )

    output = f"{repo_info['repository']}.zip"
    if repo_info["branch"]:
        output = f"{repo_info['repository']}-{repo_info['branch']}.zip"

    print(url)

    path = DOWNLOAD_DIR / output
    try:
        with download_progress:
            with httpx.Client(follow_redirects=True) as client:
                with client.stream("GET", url) as response:
                    response.raise_for_status()

                    zip_size = int(response.headers.get("Content-Length", 0))
                    task = download_progress.add_task(
                        description=f"Downloading {repo_info['repository']}",
                        total=zip_size,
                    )
                    with open(path, "wb") as f:
                        for chunk in response.iter_bytes(chunk_size=512 * 1024):
                            if chunk:
                                f.write(chunk)
                                download_progress.update(task, advance=len(chunk))

            download_progress.update(task, visible=False)
            print(f"Downloaded {repo_info['repository']} to {path}.")

    except httpx.HTTPError as e:
        handle_client_error(e)
        sys.exit(1)


async def download_single_file(
    client: httpx.AsyncClient,
    semaphore: asyncio.Semaphore,
    taskid: TaskID,
    file: dict,
) -> Path:
    path = file["path"]

    if FLATTEN:
        path = ""

    file_path = Path(DOWNLOAD_DIR / path)
    file_path.mkdir(parents=True, exist_ok=True)
    download_path = file_path / file["name"]

    if download_path.exists():
        print(f"{BRIGHT_YELLOW}{file['name']}{RESET} already exists!\n")
    else:
        async with semaphore:
            ts = int(time.time())
            url = f"{file['download_url']}?ts={ts}"

            async with client.stream("GET", url, follow_redirects=True) as response:
                response.raise_for_status()
                download_progress.update(taskid, total=int(file["size"]))

                async with aiofiles.open(download_path, "wb") as f:
                    download_progress.start_task(taskid)

                    async for chunk in response.aiter_bytes(chunk_size=512 * 1024):
                        if chunk:
                            await f.write(chunk)
                            download_progress.update(taskid, advance=len(chunk))
    return download_path


async def download_files(files: list[dict]) -> list[Path]:
    # NOTE: LIMIT PROCESSES SPAWN LIMIT IN CPU IN CASE THERE ARE THOUSANDS OF REQUESTS
    dl_semaphore = asyncio.Semaphore(DOWNLOAD_LIMIT)

    with download_progress:
        async with httpx.AsyncClient() as client:
            async with asyncio.TaskGroup() as tg:
                tasks = []
                for file in files:
                    task_id = download_progress.add_task(
                        "download", filename=file["name"], start=False
                    )
                    tasks.append(
                        tg.create_task(
                            download_single_file(
                                client,
                                dl_semaphore,
                                task_id,
                                file,
                            )
                        )
                    )

            file_paths = [task.result() for task in tasks]
    return file_paths


async def main() -> None:
    args = get_arguments()

    global DIR, BRANCH, FLATTEN, ZIP, DOWNLOAD_DIR

    if args.branch:
        BRANCH = True

    if args.flatten:
        FLATTEN = args.flatten

    if args.dir:
        DIR = args.dir

    if args.zip:
        ZIP = args.zip

    try:
        repo = parse_repo_url(args)

        print(f"{BRIGHT_GREEN}[+]{RESET} Owner: ", end="")
        print(BRIGHT_YELLOW + repo["owner"] + RESET)

        print(f"{BRIGHT_GREEN}[+]{RESET} Repository name: ", end="")
        print(BRIGHT_YELLOW + repo["repository"] + RESET)

        if repo["branch"]:
            print(f"{BRIGHT_GREEN}[+]{RESET} Branch: ", end="")
            print(BRIGHT_YELLOW + repo["branch"] + RESET)

        if repo["path"]:
            print(f"{BRIGHT_GREEN}[+]{RESET} Path: ", end="")
            print(BRIGHT_YELLOW + repo["path"] + RESET)
        print()

        # download selected files
        DOWNLOAD_DIR = Path(repo["repository"])
        DOWNLOAD_DIR.mkdir(parents=True, exist_ok=True)

        if ZIP:
            download_zip(repo)
        else:
            # fetch repository content
            files = await get_repository_content(repo)

            # select files
            selected_files = select_files(files)

            await download_files(selected_files)

            if args.rate_limit:
                check_user_rate_limit()

    except Exception as e:
        print(f"{e}")
        raise


if __name__ == "__main__":
    asyncio.run(main())
