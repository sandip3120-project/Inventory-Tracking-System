from django.test import TestCase, Client
from django.urls import reverse
from django.contrib.auth.models import User, Group

class AccessControlTests(TestCase):
    def setUp(self):
        # make a user and assign to “Operator”
        self.u = User.objects.create_user('op', password='pass')
        g = Group.objects.create(name='Operator')
        self.u.groups.add(g)
        self.client = Client()

    def test_dashboard_redirects_anonymous(self):
        r = self.client.get(reverse('dashboard'))
        self.assertRedirects(r, f"{reverse('login')}?next={reverse('dashboard')}")

    def test_dashboard_forbidden_for_operator(self):
        self.client.login(username='op', password='pass')
        r = self.client.get(reverse('dashboard'))
        self.assertEqual(r.status_code, 403)

    def test_store_allowed_for_operator(self):
        self.client.login(username='op', password='pass')
        r = self.client.get(reverse('scan-store'))
        self.assertEqual(r.status_code, 200)
