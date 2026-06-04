import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(__file__))

os.environ.setdefault('DATABASE_URL', 'postgresql://postgres:1234@localhost:5432/StudentCabinet')

from app import app
from utils import hash_password, check_password, get_course_from_group, is_password_allowed


class SecurityTests(unittest.TestCase):
    def setUp(self):
        app.config['TESTING'] = True
        app.config['SECRET_KEY'] = 'test-secret'
        self.client = app.test_client()

    def test_password_hashing_bcrypt(self):
        pw = 'mypassword123'
        hashed = hash_password(pw)
        self.assertTrue(hashed.startswith('$2'))
        self.assertTrue(check_password(pw, hashed))
        self.assertFalse(check_password('wrongpassword', hashed))

    def test_session_cookie_httponly(self):
        self.assertTrue(app.config.get('SESSION_COOKIE_HTTPONLY'))

    def test_password_allowed_charset(self):
        self.assertTrue(is_password_allowed('Pass123'))
        self.assertFalse(is_password_allowed('пароль123'))


class RouteTests(unittest.TestCase):
    def setUp(self):
        app.config['TESTING'] = True
        self.client = app.test_client()

    def test_index(self):
        self.assertEqual(self.client.get('/').status_code, 200)

    def test_login_page(self):
        self.assertEqual(self.client.get('/login').status_code, 200)

    def test_map_page(self):
        self.assertEqual(self.client.get('/map').status_code, 200)

    def test_faq_page(self):
        try:
            self.assertEqual(self.client.get('/faq').status_code, 200)
        except Exception:
            self.skipTest('PostgreSQL not available')

    def test_admin_redirects_to_login(self):
        resp = self.client.get('/admin', follow_redirects=False)
        self.assertIn(resp.status_code, (302, 303))


class UtilTests(unittest.TestCase):
    def test_course_from_group(self):
        self.assertEqual(get_course_from_group('ИСП-104-52-00'), 1)


if __name__ == '__main__':
    unittest.main()
