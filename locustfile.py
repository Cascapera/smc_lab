"""
Teste de carga com Locust.

Uso:
  1. Instale: pip install locust
  2. Inicie o servidor (ex: python manage.py runserver ou gunicorn)
  3. Rode: locust -f locustfile.py --host=http://localhost:8000
  4. Abra http://localhost:8089 e configure usuários/ramp-up
  5. Inicie o teste e observe métricas (RPS, latência, falhas)

Para linha de comando sem UI:
  locust -f locustfile.py --host=http://localhost:8000 --users 10 --spawn-rate 2 --run-time 60s --headless
"""

from locust import HttpUser, task, between


class WebsiteUser(HttpUser):
    """Simula visitantes navegando no site."""

    wait_time = between(2, 5)  # Espera 2-5s entre requests (comportamento realista)

    @task(10)
    def landing(self):
        """Página inicial - mais acessada."""
        self.client.get("/")

    @task(5)
    def planos(self):
        """Página de planos - pública."""
        self.client.get("/pagamentos/planos/")

    @task(3)
    def mural(self):
        """Mural público."""
        self.client.get("/mural/")

    @task(2)
    def recursos(self):
        """Página de recursos."""
        self.client.get("/recursos/")

    @task(1)
    def login_page(self):
        """Página de login."""
        self.client.get("/accounts/login/")


class MacroAPIsUser(HttpUser):
    """
    Simula usuários do Painel SMC (chamadas AJAX de scores e variations).
    Use quando quiser testar carga nas APIs do macro.
    """

    wait_time = between(1, 3)

    @task(5)
    def scores(self):
        self.client.get("/macro/scores/?limit=40")

    @task(5)
    def variations(self):
        self.client.get("/macro/variations/?limit=200")
