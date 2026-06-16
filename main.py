import requests
import subprocess
import sys


def get_repository_url():
    repo_url = sys.argv[1:]
    repo_contents = repo_url[0].split("/")
    return repo_contents


def fetch_files(repo_content):
    files = []
    type = []
    for content in repo_content:
        files.append(content["name"])
        type.append((content["name"], content["type"]))

    # print(content.keys())
    # print(files)
    # print(type)

    subprocess.run(
        f"{files} | fzf --prompt=' Select file >> ' --height=~50% --layout=reverse --border --exit-0",
        shell=True,
    )


def get_repository_content():
    repo = get_repository_url()
    repo_owner = repo[3]
    repo_name = repo[4]
    path = ""
    if len(repo) > 5:
        raw_path = "/".join(repo[4:])
        path = "/" + raw_path + "/"

    repo_content_raw = requests.get(
        f"https://api.github.com/repos/{repo_owner}/{repo_name}/contents/{path}"
    )
    repo_content_json = repo_content_raw.json()
    return repo_content_json


def main():
    content = get_repository_content()
    fetch_files(content)
    # print(content[4].items())


if __name__ == "__main__":
    main()
