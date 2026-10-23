import gevent
import os
import random
import uuid

from locust import HttpUser, between, events, task


AQUECIMENTO_SEGUNDOS = int(os.getenv("AQUECIMENTO_SEGUNDOS", "60"))


@events.test_start.add_listener
def reset_stats_after_warmup(environment, **kwargs):
    # Descarta as métricas do aquecimento antes de iniciar a medição.
    def reset_after_one_minute():
        gevent.sleep(AQUECIMENTO_SEGUNDOS)
        environment.runner.stats.reset_all()
        print(
            "\nAquecimento concluído: estatísticas zeradas; "
            "iniciada a medição.\n"
        )

    gevent.spawn(reset_after_one_minute)


class PetClinicBase(HttpUser):
    abstract = True
    wait_time = between(1, 3)

    def list_owners(self):
        self.client.get(
            "/api/customer/owners?lastName=",
            name="/api/customer/owners"
        )

    def get_owner(self):
        owner_id = random.randint(1, 12)
        self.client.get(
            f"/api/customer/owners/{owner_id}",
            name="/api/customer/owners/[id]"
        )

    def list_vets(self):
        self.client.get(
            "/api/vet/vets",
            name="/api/vet/vets"
        )

    def create_owner(self):
        token = uuid.uuid4().hex[:8]
        payload = {
            "firstName": f"Teste{token}",
            "lastName": "Locust",
            "address": f"Rua de Teste {token}",
            "city": "Picos",
            "telephone": str(random.randint(1000000000, 9999999999))
        }
        self.client.post(
            "/api/customer/owners",
            json=payload,
            name="/api/customer/owners [POST]"
        )


class ReadProfileUser(PetClinicBase):
    @task(45)
    def read_list_owners(self):
        self.list_owners()

    @task(35)
    def read_owner(self):
        self.get_owner()

    @task(15)
    def read_vets(self):
        self.list_vets()

    @task(5)
    def write_owner(self):
        self.create_owner()


class WriteProfileUser(PetClinicBase):
    @task(20)
    def read_list_owners(self):
        self.list_owners()

    @task(20)
    def read_owner(self):
        self.get_owner()

    @task(20)
    def read_vets(self):
        self.list_vets()

    @task(40)
    def write_owner(self):
        self.create_owner()
