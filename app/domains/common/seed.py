"""Organizations and the shared staff directory that every domain's mock data draws names from."""
from datetime import timedelta

from app.core.seedlib import SeedContext, SeedWriter

ORGANIZATIONS = [
    ("banking", "Corvane Bank", "Financial services and banking", "corvanebank.example", "London, UK", 48200,
     "Universal bank with retail, corporate and transaction banking across 31 markets."),
    ("insurance", "Harborline Mutual Insurance", "Insurance", "harborline.example", "Hartford, CT, USA", 12600,
     "Property, casualty and specialty insurer writing personal and commercial lines."),
    ("retail", "Pellwick & Co.", "Retail", "pellwick.example", "Minneapolis, MN, USA", 86000,
     "Omnichannel retailer with 640 stores, e-commerce and regional fulfilment centres."),
    ("cpg", "Fennmoor Brands", "Consumer goods", "fennmoor.example", "Amsterdam, NL", 39500,
     "Beverages, snacks, personal care and home care brands sold in 120 countries."),
    ("pharma", "Kelvaro Biosciences", "Pharma and life sciences", "kelvaro.example", "Basel, CH", 17800,
     "Research-based biopharma focused on immunology, oncology and rare disease."),
    ("healthcare", "Calderwick Health", "Healthcare", "calderwickhealth.example", "Columbus, OH, USA", 23400,
     "Integrated delivery network with 9 hospitals, 140 clinics and an owned medical group."),
    ("energy", "Brannoch Energy Networks", "Energy and utilities", "brannoch.example", "Glasgow, UK", 9100,
     "Electricity transmission and distribution operator serving 3.8M customers."),
    ("itsm", "Orvanta Group", "Cross-industry (enterprise IT shared services)", "orvanta.example", "Toronto, CA", 27000,
     "Diversified holding company whose shared-services IT desk supports every operating company."),
]

# Named staff that appear in the showcase records: (domain, first, last, title, department, roles, manager)
NAMED_STAFF = [
    ("banking", "Priya", "Raman", "Payment Operations Analyst", "Payment Operations", ["payment_ops_analyst"], "sofia.martins"),
    ("banking", "Daniel", "Okafor", "Payment Operations Analyst", "Payment Operations", ["payment_ops_analyst"], "sofia.martins"),
    ("banking", "Sofia", "Martins", "Reconciliation Team Lead", "Payment Operations", ["payment_ops_analyst", "payment_approver"], "marcus.chen"),
    ("banking", "Marcus", "Chen", "Head of Payment Operations", "Payment Operations", ["payment_approver", "payment_ops_head"], None),

    ("insurance", "Elena", "Kowalski", "FNOL Claims Handler", "Claims Intake", ["claims_handler"], "james.whitfield"),
    ("insurance", "James", "Whitfield", "Claims Triage Lead", "Claims Intake", ["claims_handler", "triage_lead"], "tom.becker"),
    ("insurance", "Aisha", "Bello", "Special Investigations Unit Investigator", "Special Investigations", ["siu_investigator"], "tom.becker"),
    ("insurance", "Tom", "Becker", "Intake Operations Manager", "Claims Intake", ["intake_manager", "triage_lead"], None),

    ("retail", "Maya", "Patel", "Customer Care Agent (Tier 1)", "Customer Care", ["cc_agent", "refund_tier1"], "grace.kim"),
    ("retail", "Liam", "O'Connor", "Customer Care Agent (Tier 2)", "Customer Care", ["cc_agent", "refund_tier2"], "grace.kim"),
    ("retail", "Grace", "Kim", "Customer Care Supervisor", "Customer Care", ["cc_agent", "cc_supervisor", "refund_supervisor"], None),

    ("cpg", "Olivia", "Pennick", "Brand Manager, Beverages", "Marketing", ["brand_manager"], "chloe.dubois"),
    ("cpg", "Rahul", "Mehta", "Regional Commercial Director, EMEA", "Sales", ["regional_manager"], None),
    ("cpg", "Chloe", "Dubois", "Commercial Finance Analyst", "Finance", ["commercial_finance"], None),
    ("cpg", "Ben", "Hartley", "Regional Sales Manager, North America", "Sales", ["regional_sales"], "rahul.mehta"),

    ("pharma", "Anna", "Lindqvist", "Senior Scientist, Bioanalytics", "Bioanalytical Sciences", ["scientist"], "kenji.watanabe"),
    ("pharma", "Kenji", "Watanabe", "Study Data Manager", "Clinical Data Management", ["data_manager"], None),
    ("pharma", "Fatima", "Haddad", "Principal Biostatistician", "Biostatistics", ["biostatistician"], None),
    ("pharma", "Peter", "Novak", "Unblinded Statistician (DMC support)", "Biostatistics", ["biostatistician", "unblinded_statistician"], "fatima.haddad"),

    ("healthcare", "Rosa", "Alvarez", "Prior Authorization Coordinator", "Patient Access", ["pa_coordinator"], "sarah.cohen"),
    ("healthcare", "David", "Nguyen", "Utilization Management Nurse", "Utilization Management", ["um_nurse"], "sarah.cohen"),
    ("healthcare", "Sarah", "Cohen", "Director, Revenue Cycle", "Revenue Cycle", ["rcm_leader"], None),
    ("healthcare", "Michael", "Osei", "Attending Physician, Orthopedics", "Orthopedics", ["clinician"], None),

    ("energy", "Carlos", "Mendes", "Field Technician (Substations)", "Field Operations", ["field_technician"], "owen.price"),
    ("energy", "Hannah", "Schmidt", "Field Technician (Distribution)", "Field Operations", ["field_technician"], "owen.price"),
    ("energy", "Owen", "Price", "Depot Supervisor", "Field Operations", ["depot_supervisor"], None),
    ("energy", "Leila", "Farah", "Dispatcher", "Network Operations", ["dispatcher"], "owen.price"),

    ("itsm", "Jordan", "Lee", "Service Desk Analyst", "IT Service Desk", ["service_desk_analyst"], "nina.petrova"),
    ("itsm", "Nina", "Petrova", "IT Operations Engineer", "IT Operations", ["it_ops", "access_fulfiller"], "erin.cho"),
    ("itsm", "Sam", "Taylor", "Software Engineer", "Engineering", ["employee"], "alex.brennan"),
    ("itsm", "Alex", "Brennan", "Engineering Manager", "Engineering", ["employee", "people_manager"], "erin.cho"),
    ("itsm", "Maria", "Santos", "Financial Analyst", "Finance", ["employee"], "kevin.walsh"),
    ("itsm", "Kevin", "Walsh", "Finance Director", "Finance", ["employee", "people_manager"], None),
    ("itsm", "Erin", "Cho", "Chief Information Security Officer", "Information Security", ["employee", "people_manager", "security_approver"], None),
]

# Named people added after all generated staff, so existing user IDs and generated names stay stable.
LATE_ADDITIONS = [
    ("retail", "Noah", "Bennett", "Customer Care Supervisor (Evenings)", "Customer Care",
     ["cc_supervisor", "refund_supervisor"], None),
]

# Additional generated staff per domain: (title, department, roles, count, manager)
GENERATED = {
    "banking": [("Payment Operations Analyst", "Payment Operations", ["payment_ops_analyst"], 8, "sofia.martins"),
                ("Senior Payment Operations Analyst", "Payment Operations", ["payment_ops_analyst", "payment_approver"], 2, "marcus.chen"),
                ("Relationship Manager", "Corporate Banking", ["relationship_manager"], 4, None)],
    "insurance": [("Claims Handler", "Claims Intake", ["claims_handler"], 10, "james.whitfield"),
                  ("Senior Claims Adjuster", "Complex Claims", ["claims_handler", "adjuster"], 4, "tom.becker"),
                  ("Underwriter", "Underwriting", ["underwriter"], 3, None)],
    "retail": [("Customer Care Agent (Tier 1)", "Customer Care", ["cc_agent", "refund_tier1"], 8, "grace.kim"),
               ("Customer Care Agent (Tier 2)", "Customer Care", ["cc_agent", "refund_tier2"], 4, "grace.kim"),
               ("Store Manager", "Stores", ["store_manager"], 3, None)],
    "cpg": [("Category Manager", "Marketing", ["brand_manager"], 3, "chloe.dubois"),
            ("Key Account Manager", "Sales", ["regional_sales"], 4, "rahul.mehta"),
            ("Commercial Finance Analyst", "Finance", ["commercial_finance"], 1, "chloe.dubois")],
    "pharma": [("Scientist", "Bioanalytical Sciences", ["scientist"], 6, "kenji.watanabe"),
               ("Clinical Data Manager", "Clinical Data Management", ["data_manager"], 2, "kenji.watanabe"),
               ("Biostatistician", "Biostatistics", ["biostatistician"], 2, "fatima.haddad")],
    "healthcare": [("Prior Authorization Coordinator", "Patient Access", ["pa_coordinator"], 6, "sarah.cohen"),
                   ("Utilization Management Nurse", "Utilization Management", ["um_nurse"], 2, "sarah.cohen"),
                   ("Attending Physician", "Medical Group", ["clinician"], 4, None)],
    "energy": [("Field Technician", "Field Operations", ["field_technician"], 10, "owen.price"),
               ("Dispatcher", "Network Operations", ["dispatcher"], 2, "owen.price"),
               ("Asset Planner", "Asset Management", ["asset_planner"], 2, None)],
    "itsm": [("Software Engineer", "Engineering", ["employee"], 10, "alex.brennan"),
             ("Data Analyst", "Data & Analytics", ["employee"], 4, "kevin.walsh"),
             ("Financial Analyst", "Finance", ["employee"], 4, "kevin.walsh"),
             ("Account Executive", "Sales", ["employee"], 6, None),
             ("HR Business Partner", "People", ["employee"], 3, None),
             ("Service Desk Analyst", "IT Service Desk", ["service_desk_analyst"], 3, "nina.petrova"),
             ("IT Operations Engineer", "IT Operations", ["it_ops", "access_fulfiller"], 2, "erin.cho")],
}

LOCATIONS = {
    "banking": [("London", "EMEA"), ("New York", "AMER"), ("Singapore", "APAC"), ("Frankfurt", "EMEA")],
    "insurance": [("Hartford", "AMER"), ("Chicago", "AMER"), ("Dallas", "AMER")],
    "retail": [("Minneapolis", "AMER"), ("Columbus", "AMER"), ("Phoenix", "AMER")],
    "cpg": [("Amsterdam", "EMEA"), ("Chicago", "AMER"), ("Singapore", "APAC"), ("Sao Paulo", "LATAM")],
    "pharma": [("Basel", "EMEA"), ("Cambridge, MA", "AMER"), ("Tokyo", "APAC")],
    "healthcare": [("Columbus", "AMER"), ("Dayton", "AMER"), ("Cincinnati", "AMER")],
    "energy": [("Glasgow", "EMEA"), ("Edinburgh", "EMEA"), ("Aberdeen", "EMEA")],
    "itsm": [("Toronto", "AMER"), ("New York", "AMER"), ("London", "EMEA"), ("Bangalore", "APAC")],
}


def _email(first: str, last: str, org_domain: str) -> str:
    clean = lambda s: "".join(ch for ch in s.lower() if ch.isalnum())  # noqa: E731
    return f"{clean(first)}.{clean(last)}@{org_domain}"


def seed(w: SeedWriter, ctx: SeedContext) -> None:
    orgs = [
        {"id": k, "name": n, "industry": i, "email_domain": d, "headquarters": h, "employees": e, "description": desc}
        for k, n, i, d, h, e, desc in ORGANIZATIONS
    ]
    ctx.run.organizations.extend(orgs)
    w.insert("common.organizations", orgs)
    domain_of = {o["id"]: o["email_domain"] for o in orgs}

    users: list[dict] = []
    by_key: dict[tuple[str, str], dict] = {}
    seen_emails: set[str] = set()

    def add_user(domain, first, last, title, dept, roles, named):
        email = _email(first, last, domain_of[domain])
        if email in seen_emails:
            return None
        seen_emails.add(email)
        city, region = ctx.pick(LOCATIONS[domain])
        user = {
            "id": f"USR-{len(users) + 1:05d}",
            "email": email,
            "full_name": f"{first} {last}",
            "first_name": first,
            "last_name": last,
            "title": title,
            "department": dept,
            "domain": domain,
            "roles": roles,
            "manager_id": None,
            "location": city,
            "region": region,
            "phone": f"+1-555-{ctx.rng.randint(100, 999)}-{ctx.rng.randint(1000, 9999)}",
            "employee_type": "employee" if named or ctx.rng.random() > 0.08 else "contractor",
            "status": "active" if named or ctx.rng.random() > 0.04 else "on_leave",
            "is_named_staff": named,
            "hire_date": ctx.today - timedelta(days=ctx.rng.randint(120, 5200)),
        }
        users.append(user)
        local = email.split("@")[0]
        by_key[(domain, local)] = user
        return user

    manager_links: list[tuple[dict, str, str]] = []
    for domain, first, last, title, dept, roles, mgr in NAMED_STAFF:
        user = add_user(domain, first, last, title, dept, roles, True)
        if mgr:
            manager_links.append((user, domain, mgr))
    for domain, groups in GENERATED.items():
        for title, dept, roles, count, mgr in groups:
            for _ in range(count):
                user = None
                while user is None:
                    user = add_user(domain, ctx.fake.first_name(), ctx.fake.last_name(), title, dept, list(roles), False)
                if mgr:
                    manager_links.append((user, domain, mgr))

    for domain, first, last, title, dept, roles, mgr in LATE_ADDITIONS:
        user = add_user(domain, first, last, title, dept, roles, True)
        if user and mgr:
            manager_links.append((user, domain, mgr))

    for user, domain, mgr in manager_links:
        user["manager_id"] = by_key[(domain, mgr)]["id"]

    ctx.run.users.extend(users)
    # Insert managers before reports is unnecessary: FK is checked per statement, so one batch is fine.
    w.insert("common.users", users)
