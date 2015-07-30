from locust import HttpLocust, TaskSet, task

class UserBehavior(TaskSet):
    @task(3)
    def index(self):
        resp = self.client.get("/")

    @task(3)
    def stats(self):
        resp = self.client.get("/stats")

    @task(1)
    def dud(self):
        resp = self.client.post("/", {"dud": "dud"})

class WebsiteUser(HttpLocust):
    task_set = UserBehavior
    min_wait = 5000
    max_wait = 15000