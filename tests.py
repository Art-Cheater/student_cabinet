import os
import sys
import tempfile
import unittest
import sqlite3
from io import BytesIO

sys.path.insert(0, os.path.dirname(__file__))
from app import app, init_user_db, hash_password, check_password, get_course_from_group, is_password_allowed
from app import STUDENTS_DB


class SecurityTests(unittest.TestCase):
    def setUp(self):
        app.config['TESTING'] = True
        app.config['SECRET_KEY'] = 'test-secret'
        self.client = app.test_client()

    def test_password_hashing_bcrypt(self):
        pw = 'mypassword123'
        hashed = hash_password(pw)
        self.assertTrue(hashed.startswith('$2b$') or hashed.startswith('$2a$'),
                        'Password hash should be bcrypt format')
        self.assertTrue(check_password(pw, hashed))
        self.assertFalse(check_password('wrongpassword', hashed))

    def test_unique_salts(self):
        pw = 'samepassword'
        h1 = hash_password(pw)
        h2 = hash_password(pw)
        self.assertNotEqual(h1, h2, 'Each hash should have a unique salt')

    def test_session_cookie_httponly(self):
        self.assertTrue(app.config.get('SESSION_COOKIE_HTTPONLY'),
                        'SESSION_COOKIE_HTTPONLY must be True')

    def test_session_cookie_samesite(self):
        self.assertEqual(app.config.get('SESSION_COOKIE_SAMESITE'), 'Lax',
                         'SESSION_COOKIE_SAMESITE must be Lax')

    def test_secret_key_not_default(self):
        self.assertNotEqual(app.secret_key, 'your_secret_key_change_me_12345',
                            'Secret key should not be the default placeholder')

    def test_password_allowed_charset(self):
        self.assertTrue(is_password_allowed('Pass123'))
        self.assertFalse(is_password_allowed('пароль123'))
        self.assertFalse(is_password_allowed('pass_123'))


class AuthTests(unittest.TestCase):
    def setUp(self):
        app.config['TESTING'] = True
        app.config['SECRET_KEY'] = 'test-secret'
        self.client = app.test_client()
        self._init_test_db()

    def _init_test_db(self):
        conn = sqlite3.connect(STUDENTS_DB)
        cur = conn.cursor()
        cur.execute("DELETE FROM users WHERE email = 'test@vyatsu.ru'")
        conn.commit()
        conn.close()

    def test_register_page_loads(self):
        resp = self.client.get('/register')
        self.assertEqual(resp.status_code, 200)

    def test_login_page_loads(self):
        resp = self.client.get('/login')
        self.assertEqual(resp.status_code, 200)

    def test_login_invalid_credentials(self):
        resp = self.client.post('/login', data={
            'email': 'nonexistent@vyatsu.ru',
            'password': 'wrong'
        }, follow_redirects=True)
        self.assertEqual(resp.status_code, 200)
        self.assertIn('Неверный email или пароль'.encode('utf-8'), resp.data)

    def test_login_rejects_non_latin_password(self):
        resp = self.client.post('/login', data={
            'email': 'nonexistent@vyatsu.ru',
            'password': 'пароль123'
        }, follow_redirects=True)
        self.assertEqual(resp.status_code, 200)
        self.assertIn('Пароль может содержать только английские буквы и цифры'.encode('utf-8'), resp.data)

    def test_protected_routes_redirect(self):
        for route in ['/dashboard', '/schedule', '/student_card', '/appointment']:
            resp = self.client.get(route, follow_redirects=True)
            self.assertEqual(resp.status_code, 200)
            self.assertIn('Вход'.encode('utf-8'), resp.data,
                          f'{route} should redirect to login')


class CourseExtractionTests(unittest.TestCase):
    def test_course_from_group(self):
        self.assertEqual(get_course_from_group('ИСП-11'), 1)
        self.assertEqual(get_course_from_group('ПД-21'), 2)
        self.assertEqual(get_course_from_group('БД-31'), 3)
        self.assertEqual(get_course_from_group('ЭБ-41'), 4)

    def test_course_fallback(self):
        self.assertEqual(get_course_from_group('АБ-51'), 1)
        self.assertEqual(get_course_from_group(''), 1)


class VKCacheTests(unittest.TestCase):
    def setUp(self):
        app.config['TESTING'] = True
        self.client = app.test_client()

    def test_news_page_loads(self):
        resp = self.client.get('/news')
        self.assertEqual(resp.status_code, 200)

    def test_news_page_has_structure(self):
        resp = self.client.get('/news')
        self.assertIn('Новости'.encode('utf-8'), resp.data)


class FAQTests(unittest.TestCase):
    def setUp(self):
        app.config['TESTING'] = True
        self.client = app.test_client()

    def test_faq_page_loads(self):
        resp = self.client.get('/faq')
        self.assertEqual(resp.status_code, 200)
        self.assertIn('Часто задаваемые вопросы'.encode('utf-8'), resp.data)

    def test_faq_has_questions(self):
        resp = self.client.get('/faq')
        self.assertIn('faq-question'.encode('utf-8'), resp.data)
        self.assertIn('faq-answer'.encode('utf-8'), resp.data)


class MapTests(unittest.TestCase):
    def setUp(self):
        app.config['TESTING'] = True
        self.client = app.test_client()

    def test_map_page_loads(self):
        resp = self.client.get('/map')
        self.assertEqual(resp.status_code, 200)
        self.assertIn('Карта'.encode('utf-8'), resp.data)

    def test_map_has_yandex_api(self):
        resp = self.client.get('/map')
        self.assertIn('api-maps.yandex.ru'.encode('utf-8'), resp.data)


if __name__ == '__main__':
    unittest.main(verbosity=2)
