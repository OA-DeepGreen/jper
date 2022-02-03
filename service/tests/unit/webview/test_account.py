import time
from typing import Optional

import flask
from bs4 import BeautifulSoup

from octopus.core import app
from octopus.modules.es.testindex import ESTestCase
from service.models import Account


def _create_acc_and_login(client, **kwargs) -> Account:
    acc = _create_acc(password='default_password', block=True, **kwargs)
    resp = _login(client, acc.email, 'default_password')
    if _is_incorrect_login(resp):
        raise Exception("Unexpected login fail")
    return acc


def _login(client, username, password) -> flask.Response:
    resp = client.post('/account/login',
                       data={'username': username,
                             'password': password})
    return resp


def _create_acc(acc_id=None, email=None, password=None,
                roles: list[str] = None, block=False) -> Account:
    if acc_id is None:
        time.sleep(0.01)
        acc_id = str(time.time())
    email = email or f'{acc_id}@abc.com'
    password = password or str(time.time())

    if roles is None:
        roles = ['admin']

    acc = Account()
    acc.add_account({
        "id": acc_id,
        "role": roles,
        "email": email,
        "api_key": f'{acc_id}.api_key',
        "password": password
    })
    acc.save()

    if block:
        acc = _find_acc_unit(email, until_is_none=False)

    return acc


def _is_incorrect_login(resp: flask.Response) -> bool:
    soup = BeautifulSoup(resp.data, 'html.parser')
    return any('Incorrect username/password' in ele.text
               for ele in soup.select('article'))


def _find_acc_unit(email: str, until_is_none: bool, timeout=10) -> Optional[Account]:
    start_time = time.time()
    while True:
        acc = Account.pull_by_email(email)
        if until_is_none:
            if acc is None:
                return acc
        else:
            if acc is not None:
                return acc

        if (time.time() - start_time) > timeout:
            raise TimeoutError('find account unit fail')
        time.sleep(0.1)


def _del_acc(email, block=False) -> Optional[Account]:
    acc = Account.pull_by_email(email)
    if acc is not None:
        acc.delete()
        if block:
            _find_acc_unit(email, until_is_none=True)
    return acc


class TestModels(ESTestCase):
    def setUp(self):
        self.run_schedule = app.config.get("RUN_SCHEDULE")
        app.config["RUN_SCHEDULE"] = False

        from service import web  # setup blueprint
        web  # avoid pycharm auto cleanup the import

        super(TestModels, self).setUp()

    def tearDown(self):
        super(TestModels, self).tearDown()
        app.config["RUN_SCHEDULE"] = self.run_schedule

    def test_account_username__repository(self):
        client = app.test_client()

        # create account and login
        acc = _create_acc_and_login(client, roles=['repository'])

        # go to target page
        resp: flask.Response = client.get(f'/account/{acc.id}')
        soup = BeautifulSoup(resp.data, 'html.parser')

        # assert
        self.assertEqual(resp.status_code, 200)
        self.assertTrue(any('Institution Repository' in ele.text
                            for ele in soup.select('h2')))

        self.assert_reset_buttons_exist(soup)
        self.assert_selector_exist(soup, [f'a[href^="/account/details/{acc.id}"]', ])
        # TODO assert "Filter" licenses
        # TODO assert repo config

        self.assert_account_details(acc, soup)

    def test_account_username__publisher(self):
        client = app.test_client()

        # create account and login
        acc = _create_acc_and_login(client, roles=['publisher'])

        # go to target page
        resp: flask.Response = client.get(f'/account/{acc.id}')
        soup = BeautifulSoup(resp.data, 'html.parser')

        # assert
        self.assertEqual(resp.status_code, 200)
        self.assertTrue(any('Connecting via SFTP' in ele.text for ele in soup.select('h3')))
        self.assertTrue(any('Connecting via SWORD' in ele.text for ele in soup.select('h3')))
        self.assert_reset_buttons_exist(soup)
        self.assert_selector_exist(soup, [f'a[href^="/account/failing/{acc.id}"]',
                                          f'a[href^="/account/matching/{acc.id}"]', ])

        self.assert_account_details(acc, soup)

        acc.delete()  # cleanup, remove account

    def assert_reset_buttons_exist(self, soup):
        self.assert_selector_exist(soup, ['button#reset_password',
                                          'button#reset_email', ])

    def assert_selector_exist(self, soup: BeautifulSoup, selector_list):
        for selector in selector_list:
            print(f'working for selector [{selector}]')
            with self.subTest(selector=selector):
                self.assertIsNotNone(soup.select_one(selector))

    def assert_account_details(self, acc: Account, soup: BeautifulSoup):
        self.assertTrue(any(acc.id == e.text.strip() for e in soup.select('dd')))
        self.assertTrue(any(acc.api_key == e.text.strip() for e in soup.select('dd')))
        self.assertTrue(any(acc.email == e.text.strip() for e in soup.select('dd')))

    def test_login__incorrect(self):
        client = app.test_client()
        acc_id = f'test_acc_abc.{time.time()}'
        email = f'{acc_id}@abc.com'
        password = 'abc'

        _del_acc(email, block=True)

        resp = _login(client, email, password)
        self.assertTrue(_is_incorrect_login(resp))

    def test_login(self):
        # create account
        acc_id = f'test_acc_abc.{time.time()}'
        email = f'{acc_id}@abc.com'
        password = 'abc'

        acc = _create_acc(acc_id=acc_id, password=password, roles=['publisher'], block=True)

        # test login success
        client = app.test_client()
        # resp = _login(client, email, password)
        resp = _login(client, email, password)
        self.assertEqual(resp.status_code, 302)
        self.assertFalse(_is_incorrect_login(resp))

        acc.delete()  # cleanup, remove account
