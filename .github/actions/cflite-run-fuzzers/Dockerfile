# Copyright © Weblate contributors
#
# SPDX-License-Identifier: GPL-3.0-or-later

FROM gcr.io/oss-fuzz-base/clusterfuzzlite-run-fuzzers:v1@sha256:7eb4374c741ef46d9c9eb739b3b17a2568fff7c542707c3d8485c55870d2ae4c

# Upstream ClusterFuzzLite retries GitHub artifact listing requests but does not
# set an HTTP timeout, and it scans every artifact page in the repository when
# looking for a single named corpus/build artifact. On a busy repository this
# turns bootstrap into a repository-wide artifact crawl before it can fall back
# to the embedded seed corpus. Patch the client in place to add request
# timeouts and to use GitHub's server-side artifact-name filter.
RUN python3 - <<'PY'
from pathlib import Path

github_api_path = Path("/opt/oss-fuzz/infra/cifuzz/filestore/github_actions/github_api.py")
github_api_text = github_api_path.read_text()

request_old = "  return requests.get(*args, **kwargs)\n"
request_new = (
    "  kwargs.setdefault('timeout', (10, 20))\n"
    "  return requests.get(*args, **kwargs)\n"
)
if request_old not in github_api_text:
    raise SystemExit("ClusterFuzzLite github_api.py request helper changed upstream")
github_api_text = github_api_text.replace(request_old, request_new, 1)

list_old = """def list_artifacts(owner, repo, headers):
  \"\"\"Returns a generator of all the artifacts for |owner|/|repo|.\"\"\"
  url = _get_artifacts_list_api_url(owner, repo)
  logging.debug('Getting artifacts from: %s', url)
  return _get_items(url, headers)
"""
list_new = """def list_artifacts(owner, repo, headers, name=None):
  \"\"\"Returns a generator of artifacts for |owner|/|repo| optionally filtered by
  |name|.\"\"\"
  url = _get_artifacts_list_api_url(owner, repo)
  logging.debug('Getting artifacts from: %s', url)
  params = {'name': name} if name else None
  return _get_items(url, headers, params=params)
"""
if list_old not in github_api_text:
    raise SystemExit("ClusterFuzzLite github_api.py list_artifacts helper changed upstream")
github_api_text = github_api_text.replace(list_old, list_new, 1)

get_items_old = """def _get_items(url, headers):
  \"\"\"Generator that gets and yields items from a GitHub API endpoint (specified
  by |URL|) sending |headers| with the get request.\"\"\"
  # Github API response pages are 1-indexed.
  page_counter = 1

  # Set to infinity so we run loop at least once.
  total_num_items = float('inf')

  item_num = 0
  while item_num < total_num_items:
    params = {'per_page': _MAX_ITEMS_PER_PAGE, 'page': str(page_counter)}
    response = _do_get_request(url, params=params, headers=headers)
"""
get_items_new = """def _get_items(url, headers, params=None):
  \"\"\"Generator that gets and yields items from a GitHub API endpoint (specified
  by |URL|) sending |headers| with the get request.\"\"\"
  # Github API response pages are 1-indexed.
  page_counter = 1

  # Set to infinity so we run loop at least once.
  total_num_items = float('inf')

  item_num = 0
  while item_num < total_num_items:
    request_params = {'per_page': _MAX_ITEMS_PER_PAGE, 'page': str(page_counter)}
    if params:
      request_params.update(params)
    response = _do_get_request(url, params=request_params, headers=headers)
"""
if get_items_old not in github_api_text:
    raise SystemExit("ClusterFuzzLite github_api.py _get_items helper changed upstream")
github_api_text = github_api_text.replace(get_items_old, get_items_new, 1)
github_api_path.write_text(github_api_text)

filestore_path = Path("/opt/oss-fuzz/infra/cifuzz/filestore/github_actions/__init__.py")
filestore_text = filestore_path.read_text()

find_old = """  def _find_artifact(self, name):
    \"\"\"Finds an artifact using the GitHub API and returns it.\"\"\"
    logging.debug('Listing artifacts.')
    artifacts = self._list_artifacts()
    artifact = github_api.find_artifact(name, artifacts)
    logging.debug('Artifact: %s.', artifact)
    return artifact
"""
find_new = """  def _find_artifact(self, name):
    \"\"\"Finds an artifact using the GitHub API and returns it.\"\"\"
    logging.debug('Listing artifacts named: %s.', name)
    artifacts = self._list_artifacts(name)
    artifact = github_api.find_artifact(name, artifacts)
    logging.debug('Artifact: %s.', artifact)
    return artifact
"""
if find_old not in filestore_text:
    raise SystemExit("ClusterFuzzLite filestore _find_artifact helper changed upstream")
filestore_text = filestore_text.replace(find_old, find_new, 1)

list_old = """  def _list_artifacts(self):
    \"\"\"Returns a list of artifacts.\"\"\"
    return github_api.list_artifacts(self.config.project_repo_owner,
                                     self.config.project_repo_name,
                                     self.github_api_http_headers)
"""
list_new = """  def _list_artifacts(self, name=None):
    \"\"\"Returns a list of artifacts optionally filtered by |name|.\"\"\"
    return github_api.list_artifacts(self.config.project_repo_owner,
                                     self.config.project_repo_name,
                                     self.github_api_http_headers,
                                     name=name)
"""
if list_old not in filestore_text:
    raise SystemExit("ClusterFuzzLite filestore _list_artifacts helper changed upstream")
filestore_text = filestore_text.replace(list_old, list_new, 1)
filestore_path.write_text(filestore_text)
PY
