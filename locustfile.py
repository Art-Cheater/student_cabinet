from locust import HttpUser, task, between

class StudentUser(HttpUser):
    wait_time = between(1, 3)

    def on_start(self):
        """
        Авторизация при старте пользователя
        """
        self.login()

    def login(self):
        response = self.client.post("/login", data={
            "email": "potap1234@vyatsu.ru",
            "password": "potap1234"
        })

        # можно отследить успешный логин по редиректу или статусу
        if response.status_code not in [200, 302]:
            print("Login failed!")

    @task(4)
    def open_schedule(self):
        self.client.get("/schedule")

    @task(3)
    def open_news(self):
        self.client.get("/news")

    @task(2)
    def open_profile(self):
        self.client.get("/profile")

    @task(1)
    def open_student_card(self):
        self.client.get("/student-card")

    @task(1)
    def open_home(self):
        self.client.get("/")