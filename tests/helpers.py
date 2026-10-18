REG = {
    "company_name": "ABC Technologies",
    "email": "hr@abc.example",
    "phone": "+91 98765 43210",
    "address": "12 MG Road, Hyderabad",
    "industry": "Software",
    "username": "abctech",
    "password": "correct-horse-1",
    "confirm_password": "correct-horse-1",
}


def register(client, **over):
    return client.post("/api/auth/register", json={**REG, **over})


def login(client, username="abctech", password="correct-horse-1"):
    return client.post("/api/auth/login", json={"username": username, "password": password})


def make_account(app, n=1):
    """Create + return a logged-in test client for a distinct account."""
    c = app.test_client()
    r = register(c, username=f"user{n}", email=f"user{n}@example.com", company_name=f"Company {n}")
    assert r.status_code == 201, r.get_json()
    return c
