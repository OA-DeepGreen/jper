import io
import os
import time
from typing import Iterable, Callable, Optional

import bs4.element
import pkg_resources
from bs4 import BeautifulSoup
from flask import Response

from octopus.core import app
from octopus.modules.es.testindex import ESTestCase
from service.__utils import ez_dao_utils, ez_query_maker
from service.models import Account, LicRelatedFile, License, Alliance
from service.views import license_manage

PATH_LIC_A = '/tests/resources/new-EZB-NALIW-00493_AL.csv'
PATH_PARTI_A = '/tests/resources/EZB-NALIW-00493_OA_participants_current.csv'


def _is_incorrect_login(resp: Response) -> bool:
    soup = BeautifulSoup(resp.data, 'html.parser')
    return any('Incorrect username/password' in ele.text
               for ele in soup.select('article'))


def _login(client, username, password) -> Response:
    resp = client.post('/account/login',
                       data={'username': username,
                             'password': password})
    return resp


def _login_as_admin(client):
    resp = _login(client, 'green@deepgreen.org', 'admin')
    if _is_incorrect_login(resp):
        raise Exception("Unexpected login fail")


def load_file_for_upload(file_path: str) -> io.BytesIO:
    file_bytes: io.BufferedReader = pkg_resources.resource_stream('service', file_path)
    lic_bytes = io.BytesIO(file_bytes.read())
    lic_bytes.name = file_bytes.name.split('/')[-1]
    return lic_bytes


def send_upload_lic(client,
                    file_path: str,
                    lic_type: str = 'alliance',
                    follow_redirects=False) -> Response:
    post_data = {
        'file': load_file_for_upload(file_path),
        'lic_type': lic_type,
    }

    # run
    resp: Response = client.post('/license-manage/upload-license', data=post_data,
                                 follow_redirects=follow_redirects)
    return resp


def send_deactivate_license(client, lic_lrf_id: str,
                            parti_lrf_id: str = None,
                            follow_redirects=False) -> Response:
    post_data = dict(lic_lrf_id=lic_lrf_id)
    if parti_lrf_id:
        post_data['parti_lrf_id'] = parti_lrf_id
    resp: Response = client.post('/license-manage/deactivate-license',
                                 data=post_data,
                                 follow_redirects=follow_redirects)
    return resp


def send_active_lic_related_file(client, lrf_id: str, follow_redirects=False) -> Response:
    resp: Response = client.post('/license-manage/active-lic-related-file',
                                 data={'lrf_id': lrf_id, },
                                 follow_redirects=follow_redirects)
    return resp


class LicDetailPageHelper:
    def __init__(self, html):
        self.soup = BeautifulSoup(html, 'lxml')

    def active_history_table(self) -> tuple:
        table_ele_list = self.soup.select('table')
        active_tbl, history_tbl = table_ele_list
        return active_tbl, history_tbl

    def active_tbl(self):
        return self.active_history_table()[0]

    def history_tbl(self):
        return self.active_history_table()[1]

    @staticmethod
    def cnt_table_row(soup):
        return len(soup.select('tr')) - 1  # -1 for not include header

    def n_active_row(self):
        active_tbl, _ = self.active_history_table()
        return self.cnt_table_row(active_tbl)

    def n_history_row(self):
        _, history_tbl = self.active_history_table()
        rows = [r for r in history_tbl.select('tr') if 'detail_row' not in r.get('class', [])]
        return len(rows)

    def non_active_lrf_id_list(self) -> Iterable[str]:
        lrf_id_list = (i.get('value') for i in self.history_tbl().select('input[type=hidden][name=lrf_id]'))
        lrf_id_list = filter(None, lrf_id_list)
        return lrf_id_list

    def find_active_row_by_lrf_id(self, lrf_id: str) -> bs4.element.Tag:
        rows = self.active_tbl().select('tr')
        rows = [r for r in rows
                if r.select(f'input[value="{lrf_id}"]')]
        return rows[0] if rows else None


def load_lic_detail_page_helper(client) -> LicDetailPageHelper:
    resp: Response = client.get('/license-manage/')
    return LicDetailPageHelper(resp.data)


class TestLicenseManage(ESTestCase):
    def setUp(self):
        self.run_schedule = app.config.get("RUN_SCHEDULE")
        app.config["RUN_SCHEDULE"] = False

        from service import web  # setup blueprint
        web  # avoid pycharm auto cleanup the import

        super(TestLicenseManage, self).setUp()

    def tearDown(self):
        super(TestLicenseManage, self).tearDown()
        app.config["RUN_SCHEDULE"] = self.run_schedule

    def test_details__normal(self):
        client = app.test_client()
        _login_as_admin(client)

        resp: Response = client.get('/license-manage/')

        self.assertEqual(resp.status_code, 200)
        soup = BeautifulSoup(resp.data, 'lxml')

        h2_text_list = [e.text for e in soup.select('h2')]
        for t in ['Upload License', 'Current License Files', 'History']:
            self.assertIn(t, h2_text_list)

        table_ele_list = soup.select('table')
        self.assertEqual(len(table_ele_list), 2)

        active_tbl, history_tbl = table_ele_list

        self.assertGreater(len(active_tbl.select('tr')), 0)
        self.assertGreater(len(history_tbl.select('tr')), 0)

    def test_details__not_admin(self):
        client = app.test_client()

        acc = Account()
        acc_id = str(time.time())
        acc.add_account({
            "id": acc_id,
            "role": ['publisher'],
            "email": f'{acc_id}@abc.com',
            "api_key": f'{acc_id}.api_key',
            "password": 'password',
        })
        acc.save()
        ez_dao_utils.wait_unit_id_found(Account, acc_id)

        resp = _login(client, acc.email, 'password')
        if _is_incorrect_login(resp):
            raise Exception("Unexpected login fail")

        resp: Response = client.get('/license-manage/')

        self.assertEqual(resp.status_code, 401)

    def test_upload_license__normal(self):
        client = app.test_client()
        _login_as_admin(client)

        # prepare data for assert
        org_size = LicRelatedFile.count(ez_query_maker.match_all())
        org_detail_page = load_lic_detail_page_helper(client)
        org_lrf_id_list = set(org_detail_page.non_active_lrf_id_list())

        # run
        resp: Response = send_upload_lic(client, PATH_LIC_A,
                                         lic_type='alliance', follow_redirects=True)

        # assert
        new_size = LicRelatedFile.count(ez_query_maker.match_all())
        self.assertGreater(new_size, org_size)

        detail_page = LicDetailPageHelper(resp.data)
        self.assertEqual(detail_page.n_active_row(), org_detail_page.n_active_row())
        self.assertGreater(detail_page.n_history_row(), org_detail_page.n_history_row())

        new_lrf_id_list = set(detail_page.non_active_lrf_id_list())
        diff_lrf_id_list = new_lrf_id_list - org_lrf_id_list
        self.assertEqual(len(diff_lrf_id_list), 1)

        # assert LicRelatedFile
        new_lrf_id = next(iter(diff_lrf_id_list))
        lrf: LicRelatedFile = ez_dao_utils.pull_by_id(LicRelatedFile, new_lrf_id)
        self.assertIsNotNone(lrf)
        self.assertTrue(lrf.is_license())
        self.assertEqual(lrf.status, "validation passed")
        self.assertFalse(lrf.is_active())

        # assert License
        ez_dao_utils.wait_unit_id_found(License, lrf.record_id)
        lic: License = ez_dao_utils.pull_by_id(License, lrf.record_id)
        self.assertFalse(lic.is_active())
        self.assertGreater(len(lic.identifiers), 0)
        self.assertEqual(lrf.ezb_id, lic.get_first_ezb_id())

        # check file saved to hard disk
        # print(lrf.file_name)
        self.assertTrue(license_manage.
                        _path_lic_related_file(lrf.file_name)
                        .is_file())

        # clean table
        delete_lrf(lrf)

    def test_upload_license__invalid_lic_file(self):
        client = app.test_client()
        _login_as_admin(client)

        # prepare data for assert
        org_detail_page = load_lic_detail_page_helper(client)

        lrf_finder = create_new_lrf_finder()

        # run
        resp: Response = send_upload_lic(client, PATH_PARTI_A,
                                         lic_type='alliance', follow_redirects=True)
        self.assertEqual(resp.status_code, 400)

        time.sleep(3)  # wait for lrf saved
        new_detail_page = load_lic_detail_page_helper(client)

        # assert new history rows
        self.assertGreater(new_detail_page.n_history_row(),
                           org_detail_page.n_history_row())

        # assert lrf
        lrf = lrf_finder()
        self.assertIsNotNone(lrf)
        self.assertEqual(lrf.status, 'validation failed')
        self.assertIsNotNone(lrf.data.get('validation_notes'))

    def test_upload_license__duplicate_upload(self):
        client = app.test_client()
        _login_as_admin(client)

        lrf1 = self.do_upload_active_lic(client)
        time.sleep(3)  # wait for license update
        self.assert_only_one_ezb_id_active(lrf1.ezb_id, lrf1.record_id)
        lrf2 = self.do_upload_active_lic(client)
        time.sleep(3)  # wait for license update
        self.assert_only_one_ezb_id_active(lrf2.ezb_id, lrf2.record_id)

        lrf1 = ez_dao_utils.pull_by_id(LicRelatedFile, lrf1.id)
        self.assertFalse(lrf1.is_active())
        lic1 = ez_dao_utils.pull_by_id(License, lrf1.record_id)
        self.assertFalse(lic1.is_active())

        lrf2 = ez_dao_utils.pull_by_id(LicRelatedFile, lrf2.id)
        self.assertTrue(lrf2.is_active())
        lic2 = ez_dao_utils.pull_by_id(License, lrf2.record_id)
        self.assertTrue(lic2.is_active())

        delete_lrf(lrf1)
        delete_lrf(lrf2)

    def do_upload_active_lic(self, client, lic_path: str = None) -> LicRelatedFile:
        lic_path = lic_path or PATH_LIC_A

        # upload
        lrf_finder = create_new_lrf_finder()
        resp: Response = send_upload_lic(client, lic_path,
                                         lic_type='alliance', follow_redirects=False)
        self.assertEqual(resp.status_code, 302)

        # wait for lic created
        lrf1 = lrf_finder()
        ez_dao_utils.wait_unit_id_found(License, lrf1.record_id)

        # active
        resp: Response = send_active_lic_related_file(client, lrf1.id, follow_redirects=False)
        self.assertEqual(resp.status_code, 302)

        # check active
        lrf1: LicRelatedFile = ez_dao_utils.pull_by_id(LicRelatedFile, lrf1.id)
        self.assertTrue(lrf1.is_active())

        return lrf1

    def do_upload_active_parti(self, client, lic_lrf_id: str, parti_path: str = None) -> LicRelatedFile:
        parti_path = parti_path or PATH_PARTI_A

        lrf_finder = create_new_lrf_finder()

        post_data = dict(lic_lrf_id=lic_lrf_id,
                         file=load_file_for_upload(parti_path), )
        resp = client.post('/license-manage/upload-participant',
                           data=post_data,
                           follow_redirects=False)
        self.assertEqual(resp.status_code, 302)

        # active
        parti_lrf = lrf_finder()
        resp = send_active_lic_related_file(client, parti_lrf.id, follow_redirects=False)
        self.assertEqual(resp.status_code, 302)

        parti_lrf = reload_lrf(parti_lrf)

        return parti_lrf

    def assert_only_one_ezb_id_active(self, ezb_id: str, lic_id: str):
        lic_id_list = (lrf.record_id for lrf in LicRelatedFile.pull_all_by_query_str('ezb_id', ezb_id)
                       if lrf.is_license())
        lic_list = (ez_dao_utils.pull_by_id(License, _id) for _id in lic_id_list)
        lic_list = [l for l in lic_list if l.is_active()]
        self.assertEqual(len(lic_list), 1)
        self.assertEqual(lic_list[0].id, lic_id)

    def test_active_lic_related_file__normal(self):
        client = app.test_client()
        _login_as_admin(client)

        # prepare upload / validation passed record
        new_lrf_finder = create_new_lrf_finder()
        resp: Response = send_upload_lic(client, PATH_LIC_A,
                                         lic_type='alliance', follow_redirects=True)
        self.assertEqual(resp.status_code, 200)
        new_lrf = new_lrf_finder()
        self.assertIsNotNone(new_lrf)

        # deactivate all lrf
        for checker in [license_manage._deactivate_lrf_by_lrf_id(lrf.id, License) for lrf in
                        LicRelatedFile.pull_all_by_status('active')]:
            checker()

        old_page = load_lic_detail_page_helper(client)
        incorrect_id_list = {l.id for l in License.pull_all_by_status_and_id('active', new_lrf.ezb_id)}

        # run
        resp: Response = send_active_lic_related_file(client, new_lrf.id, follow_redirects=True)
        self.assertEqual(resp.status_code, 200)

        # assert new active lrf record in table
        new_page = LicDetailPageHelper(resp.data)
        self.assertLess(old_page.n_active_row(),
                        new_page.n_active_row(), )

        self.assertTrue(new_lrf.is_license())

        # only one active record for each ezb_id
        time.sleep(3)  # wait for License.save()
        active_lic_id_list = {l.id for l in License.pull_all_by_status_and_id('active', new_lrf.ezb_id)}
        active_lic_id_list = active_lic_id_list - incorrect_id_list
        self.assertEqual(len(list(active_lic_id_list)), 1)

        # cleanup
        delete_lrf(new_lrf)

    def test_deactivate_license__normal_lic_only(self):
        client = app.test_client()
        _login_as_admin(client)

        lrf = self.do_upload_active_lic(client)

        old_detail_page = load_lic_detail_page_helper(client)

        resp = send_deactivate_license(client, lrf.id, follow_redirects=True)
        new_detail_page = LicDetailPageHelper(resp.data)

        self.assertGreater(new_detail_page.n_history_row(),
                           old_detail_page.n_history_row())

        self.assertLess(new_detail_page.n_active_row(),
                        old_detail_page.n_active_row())

        delete_lrf(lrf)

    def test_deactivate_license__normal_lic_parti(self):
        client = app.test_client()
        _login_as_admin(client)

        # setup
        lic_lrf = self.do_upload_active_lic(client)
        parti_lrf = self.do_upload_active_parti(client, lic_lrf.id)
        self.assertTrue(lic_lrf.is_active())
        self.assertTrue(parti_lrf.is_active())

        old_page = load_lic_detail_page_helper(client)

        # run
        resp = send_deactivate_license(client, lic_lrf.id, parti_lrf_id=parti_lrf.id,
                                       follow_redirects=True)
        new_page = LicDetailPageHelper(resp.data)

        # assert
        lic_lrf = reload_lrf(lic_lrf)
        self.assertFalse(lic_lrf.is_active())
        parti_lrf = reload_lrf(parti_lrf)
        self.assertFalse(parti_lrf.is_active())

        self.assertGreater(old_page.n_active_row(),
                           new_page.n_active_row(), )
        self.assertLess(old_page.n_history_row(),
                        new_page.n_history_row(), )

        delete_lrf(lic_lrf)
        delete_lrf(parti_lrf)

    def test_upload_parti__normal(self):
        client = app.test_client()
        _login_as_admin(client)

        lic_lrf = self.do_upload_active_lic(client)
        self.assertTrue(lic_lrf.is_active())
        self.assertTrue(lic_lrf.is_license())

        old_page = load_lic_detail_page_helper(client)
        lrf_row = old_page.find_active_row_by_lrf_id(lic_lrf.id)
        self.assertIsNotNone(lrf_row)
        self.assertEqual(len(lrf_row.select('form[action="/license-manage/upload-participant"]')), 1)

        # run upload-participant

        lrf_finder = create_new_lrf_finder()

        post_data = dict(lic_lrf_id=lic_lrf.id,
                         file=load_file_for_upload(PATH_PARTI_A), )
        client.post('/license-manage/upload-participant',
                    data=post_data,
                    follow_redirects=False)

        # assert parti lrf created
        lrf = lrf_finder()
        self.assertFalse(lrf.is_license())
        self.assertEqual(lrf.status, 'validation passed')

        # run active parti
        resp = send_active_lic_related_file(client, lrf.id, follow_redirects=True)

        #  assert lrf active and UI
        lrf: LicRelatedFile = ez_dao_utils.pull_by_id(LicRelatedFile, lrf.id)
        self.assertTrue(lrf.is_active())

        new_page = LicDetailPageHelper(resp.data)

        self.assertEqual(old_page.n_active_row(),
                         new_page.n_active_row())

        lrf_row = new_page.find_active_row_by_lrf_id(lic_lrf.id)
        self.assertIsNotNone(lrf_row)
        self.assertEqual(len(lrf_row.select('form[action="/license-manage/upload-participant"]')), 0)
        self.assertEqual(len(lrf_row.select('form[action="/license-manage/update-participant"]')), 1)
        self.assertEqual(len(lrf_row.select('form[action="/license-manage/deactivate-participant"]')), 1)

        delete_lrf(lrf)
        delete_lrf(lic_lrf)

    def test_update_license__normal(self):
        client = app.test_client()
        _login_as_admin(client)

        # setup
        lic_lrf = self.do_upload_active_lic(client)
        parti_lrf = self.do_upload_active_parti(client, lic_lrf.id, )
        self.assertTrue(lic_lrf.is_active())
        self.assertTrue(parti_lrf.is_active())
        self.assertEqual(lic_lrf.id, parti_lrf.data.get("lic_related_file_id"))

        old_page = load_lic_detail_page_helper(client)

        lrf_finder = create_new_lrf_finder()

        # run update-license
        resp: Response = client.post('/license-manage/update-license',
                                     data=dict(
                                         lic_lrf_id=lic_lrf.id,
                                         parti_lrf_id=parti_lrf.id,
                                         file=load_file_for_upload(PATH_LIC_A),
                                     ),
                                     follow_redirects=True)
        new_page = LicDetailPageHelper(resp.data)

        lic_lrf = reload_lrf(lic_lrf)
        self.assertFalse(lic_lrf.is_active())
        parti_lrf = reload_lrf(parti_lrf)
        self.assertTrue(parti_lrf.is_active())

        new_lic_lrf = lrf_finder()
        self.assertTrue(new_lic_lrf.is_license())
        self.assertTrue(new_lic_lrf.is_active())
        self.assertEqual(new_lic_lrf.id, parti_lrf.data.get("lic_related_file_id"))

        self.assertEqual(old_page.n_active_row(),
                         new_page.n_active_row())
        self.assertLess(old_page.n_history_row(),
                        new_page.n_history_row())

        delete_lrf(parti_lrf)
        delete_lrf(lic_lrf)
        delete_lrf(new_lic_lrf)

    def test_delete_lic_related_file__normal(self):
        client = app.test_client()
        _login_as_admin(client)

        # setup
        lic_lrf = self.do_upload_active_lic(client)
        license_manage._deactivate_lrf_by_lrf_id(lic_lrf.id, License)()
        lic_lrf = reload_lrf(lic_lrf)
        self.assertFalse(lic_lrf.is_active())
        self.assertTrue(license_manage._path_lic_related_file(lic_lrf.file_name).is_file())
        old_page = load_lic_detail_page_helper(client)

        # run
        resp: Response = client.post('/license-manage/delete-lic-related-file',
                                     data=dict(lrf_id=lic_lrf.id),
                                     follow_redirects=True)
        new_page = LicDetailPageHelper(resp.data)

        # assert
        self.assertEqual(old_page.n_active_row(),
                         new_page.n_active_row())
        self.assertGreater(old_page.n_history_row(),
                           new_page.n_history_row())
        self.assertFalse(license_manage._path_lic_related_file(lic_lrf.file_name).is_file())
        self.assertIsNone(ez_dao_utils.pull_by_id(LicRelatedFile, lic_lrf.id))

        time.sleep(3)  # wait for license deleted
        self.assertIsNone(lic_lrf.get_related_record())

        delete_lrf(lic_lrf)

    def test_do_upload_active_lic(self):
        client = app.test_client()
        _login_as_admin(client)

        self.do_upload_active_lic(client)

    def test_do_upload_active_parti(self):
        client = app.test_client()
        _login_as_admin(client)

        lic_lrf = self.do_upload_active_lic(client)
        self.do_upload_active_parti(client, lic_lrf.id)


def reload_lrf(lrf: LicRelatedFile) -> LicRelatedFile:
    lrf: LicRelatedFile = ez_dao_utils.pull_by_id(LicRelatedFile, lrf.id)
    return lrf


def delete_lrf(lrf: LicRelatedFile):
    if lrf.is_license():
        rec_cls = License
    else:
        rec_cls = Alliance
    rec = ez_dao_utils.pull_by_id(rec_cls, lrf.record_id)
    if rec:
        rec.delete()

    lrf.delete()

    file_path = license_manage._path_lic_related_file(lrf.file_name)
    if file_path.is_file():
        os.remove(file_path)


def create_new_lrf_finder() -> Callable[[], Optional[LicRelatedFile]]:
    size = 1000
    org_lrf_id_list = {lrf.id for lrf in ez_dao_utils.query_objs(LicRelatedFile, ez_query_maker.match_all(size=size))}

    def _fn():
        new_lrf_list = ez_dao_utils.query_objs(LicRelatedFile, ez_query_maker.match_all(size=size))
        diff_lrf_list = [lrf for lrf in new_lrf_list if lrf.id not in org_lrf_id_list]
        return diff_lrf_list[0] if diff_lrf_list else None

    return _fn


def pull_all_by_status(status):
    query = {
        "query": {
            "match": {
                "status": status
            }
        }
    }
    results = ez_dao_utils.query_objs(LicRelatedFile, query)
    return results
