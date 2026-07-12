## Todos

- [ ] Convert the program into CLI.
- [x] Use `click` or `argparse` for better CLI tool management
- [ ] Add file download progress bar
- [ ] Download path feature
- [x] Specific branch feature
- [ ] `fzf` alternative if it not installed
- [x] preserve the path of the file, download files in the respective directory structure
- [x] download files in the directory same as repository name instea of `filehub_downloads`
- [x] handle if the repository URL is not provided.
- [x] check if the provided url is a Github url
- [ ] handle if github repo doesn't exits
- [x] if the file github url is provided, download it directly
- [x] handle the branch name if it's provided in the URL
- [ ] handle program cancellation using `CTRL+C`
- [ ] handle root directory cleanup if exited unexpectedly
- [ ] check internet connectivity
- [ ] user authentication for more api requests
- [x] check if branch exits or not
- [x] add flag such as `--preserve-path` or `--flaten` for whether to preserve the directory structure or keep it concise
- [ ] set CPU limit flag `-c` or `--cpu` to let users specifiy the number of files to be downloaded at a time.
- [x] add option such as `-z` or `--zip` to download the zip archive of the repository.

- [ ] if fzf is not installed then we can make optional using `--fzf` and ask users to provide the file names manually on input?
- [x] use API response headers `X-RateLimit-Limit`, `X-RateLimit-Remaining` and `X-RateLimit-Reset` to check the rate-limit instead of making requests on `rate-limi/` endpoint at every start and end of the program.
- [ ] consider using Git Trees API with `recursive=1` parameter, to fetch the entire repository tree in a single request

- [ ] lazy browsing, instead of making 1000s of calls for each directory, let user the choose the directory and then make the call
- [x] create a flag to let user check their rate limit maybe `--rate-limit`
- [ ] select files using fzf

- [ ] download from gist
- [x] download complete directory

> [!ERROR] ERROR [fixed]
> handle the only file url error

> [!NOTE] NOTE [fixed]
> if in case branch name looks like a path such as `feat/jobdori-122b-doctor-broad-cwd` then it might cause an error as we cannot find the branch in the URL and it might get included in the path segment of urlparse. To avoid this, loop over the path segements and make api calls until we get the 200 status and find the right branch

- Main
  default branch root url : `https://github.com/abhicodes07/test-repo` or `https://github.com/abhicodes07/test-repo/tree/main`
  default branch directory url : `https://github.com/abhicodes07/test-repo/tree/main/dev`
  default branch file url : `https://github.com/abhicodes07/test-repo/blob/main/dev/seventh.txt`

- master
  file url on master branch : `https://github.com/abhicodes07/test-repo/blob/master/src/sixth.txt`
  some directory on master branch: `https://github.com/abhicodes07/test-repo/tree/master/src`
  root url : `https://github.com/abhicodes07/test-repo/tree/master`

- some url: `https://github.com/openclaw/openclaw/tree/feat/azure-mai-models/config/tsconfig` where branch is `feat/azure-mai-models`
- file url: `https://github.com/openclaw/openclaw/blob/feat/azure-mai-models/config/tsconfig/oxlint.extensions.json`

## Behaviour

If default unauthorized API access rate exceeded, then automatically switch to use authentication if provided using few methods.
To avoid this, use `--use-auth` option to always use authenticated requests.

## Resources

- [Progress bar](https://stackoverflow.com/questions/6415402/creating-a-progress-bar-in-a-cli-application)
- [Click module](https://realpython.com/python-click/#creating-command-line-interfaces-with-click-and-python)
- [Packaging CLI Tool](https://packaging.python.org/en/latest/guides/creating-command-line-tools/)
- [argparsing](https://gist.github.com/abalter/605773b34a68bb370bf84007ee55a130)

- [selectable interface, maybe](https://github.com/dmartinezm/cli_table_scroll/tree/master)

- [custom argparse help](https://gist.github.com/fonic/fe6cade2e1b9eaf3401cc732f48aeebd)
