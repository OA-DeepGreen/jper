from io import TextIOWrapper
from typing import Optional

from flask import request, abort

from octopus.core import app
from service import models
from flask_login import current_user


def get_req_page_num() -> int:
    page_num = int(request.values.get("page", app.config.get("DEFAULT_LIST_PAGE_START", 1)))
    return page_num


def set_repo_config_by_req_files(rec: models.RepositoryConfig, repo: str, encoding='utf-8') -> bool:
    saved = None
    io_wrapper = TextIOWrapper(request.files['file'], encoding=encoding)
    if request.files['file'].filename.endswith('.csv'):
        saved = rec.set_repo_config(csvfile=io_wrapper, repository=repo)
    elif request.files['file'].filename.endswith('.txt'):
        saved = rec.set_repo_config(textfile=io_wrapper, repository=repo)
    return saved


def find_repo_config(repo_id: str) -> Optional[models.RepositoryConfig]:
    app.logger.debug(current_user.id + " " + request.method + " to config route")
    if repo_id is None:
        if current_user.has_role('repository'):
            repo_id = current_user.id
        elif current_user.has_role('admin'):
            return None  # the admin cannot do anything at /config, but gets a 200 so it is clear they are allowed
        else:
            abort(400)
    elif not current_user.has_role('admin'):  # only the superuser can set a repo id directly
        abort(401)
    rec = models.RepositoryConfig().pull_by_repo(repo_id)
    if rec is None:
        rec = models.RepositoryConfig()
        rec.repo = repo_id
        # rec.repository = repoid
        # 2016-09-16 TD : The field 'repository' has changed to 'repo' due to
        #                 a bug fix coming with a updated version ES 2.3.3
    return rec
