from django.db import migrations

JOBS = [
    {
        "title": "Backend Engineer",
        "department": "Engineering",
        "raw_jd_text": (
            "We're looking for a Backend Engineer to design and build reliable APIs and "
            "data pipelines. You'll work with Python/Django, PostgreSQL, and async task "
            "queues, and collaborate closely with frontend and product teams."
        ),
        "required_skills": ["Python", "Django", "PostgreSQL", "REST APIs", "Celery"],
    },
    {
        "title": "Frontend Engineer",
        "department": "Engineering",
        "raw_jd_text": (
            "We're looking for a Frontend Engineer to build fast, accessible user "
            "interfaces with React and Next.js, working closely with designers and "
            "backend engineers to ship end-to-end features."
        ),
        "required_skills": ["JavaScript", "TypeScript", "React", "Next.js", "CSS"],
    },
    {
        "title": "Data Scientist",
        "department": "Data",
        "raw_jd_text": (
            "We're looking for a Data Scientist to build models and analyses that drive "
            "product decisions, working with large datasets in Python and SQL."
        ),
        "required_skills": ["Python", "SQL", "Machine Learning", "Statistics", "Pandas"],
    },
]


def seed_jobs(apps, schema_editor):
    JobPosition = apps.get_model("jobs", "JobPosition")
    for job in JOBS:
        JobPosition.objects.get_or_create(title=job["title"], defaults=job)


def unseed_jobs(apps, schema_editor):
    JobPosition = apps.get_model("jobs", "JobPosition")
    JobPosition.objects.filter(title__in=[job["title"] for job in JOBS]).delete()


class Migration(migrations.Migration):
    dependencies = [
        ("jobs", "0001_initial"),
    ]

    operations = [
        migrations.RunPython(seed_jobs, unseed_jobs),
    ]
