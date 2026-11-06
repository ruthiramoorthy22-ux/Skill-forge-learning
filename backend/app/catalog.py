"""Catalog data for Skill Forge Learning (Phase 1).

Phase 1 serves the catalog from this module. Phase 2 moves it into PostgreSQL.
Levels are PROVISIONAL: each category's topics are split into thirds by their
listed order (beginner, intermediate, advanced). Admins will set real levels later.
No lessons exist yet, so no course is "available". "in_development" marks the
courses that get seeded lesson content first.
"""
import re

_RAW = [
    ("programming-languages", "Programming Languages",
     "C;C++;Java;Python;JavaScript;TypeScript;C#;Go;Rust;PHP;Ruby;Kotlin;Swift;Dart;R;Bash and Shell Scripting"),
    ("web-development", "Web Development",
     "HTML5;CSS3;Responsive Web Design;JavaScript;ES6+;DOM Manipulation;Browser APIs;Bootstrap;Tailwind CSS;React;Next.js;Node.js;Express.js;REST APIs;Web Authentication;Full-Stack Development;Website Testing;Website Deployment"),
    ("mobile-app-development", "Mobile App Development",
     "Android Fundamentals;Kotlin;Flutter;Dart;SwiftUI;React Native;Mobile UI Design;API Integration;Firebase;Push Notifications;Mobile App Testing;APK Generation;App Release and Deployment"),
    ("data-structures-algorithms", "Data Structures and Algorithms",
     "Time Complexity;Space Complexity;Arrays;Strings;Linked Lists;Stacks;Queues;Hash Tables;Trees;Binary Search Trees;Heaps;Graphs;Recursion;Backtracking;Sorting Algorithms;Searching Algorithms;Two Pointers;Sliding Window;Greedy Algorithms;Dynamic Programming;Graph Traversal;Shortest Path Algorithms;Interview Coding Problems;Competitive Programming Fundamentals"),
    ("ai-machine-learning", "Artificial Intelligence and Machine Learning",
     "Mathematics for AI;Python for AI;NumPy;Pandas;Data Preprocessing;Feature Engineering;Exploratory Data Analysis;Supervised Learning;Unsupervised Learning;Regression;Classification;Decision Trees;Random Forest;Support Vector Machines;Clustering;Dimensionality Reduction;Neural Networks;Deep Learning;Natural Language Processing;Computer Vision;Generative AI;Large Language Models;Prompt Engineering;AI Agents;Model Evaluation;Model Deployment;MLOps;Responsible AI"),
    ("data-science-analytics", "Data Science and Analytics",
     "Statistics;Probability;Data Collection;Data Cleaning;Exploratory Data Analysis;Data Visualization;Python for Data Science;NumPy;Pandas;SQL for Analytics;Excel;Power BI;Tableau;Business Analytics;Dashboard Development"),
    ("database-backend", "Database and Backend",
     "SQL;MySQL;PostgreSQL;SQLite;MongoDB;Database Design;Entity Relationship Modeling;Normalization;Primary and Foreign Keys;Joins;Subqueries;Indexes;Transactions;JDBC;Object Relational Mapping;Redis;REST API Development;Backend Authentication;Database Security"),
    ("cloud-devops", "Cloud and DevOps",
     "Linux;Command-Line Fundamentals;Git;GitHub;GitLab;Docker;Kubernetes;CI/CD;AWS;Microsoft Azure;Google Cloud;Terraform;Jenkins;Application Deployment;Monitoring;Logging;Infrastructure Fundamentals;Cloud Security"),
    ("cybersecurity", "Cybersecurity",
     "Computer Networking;Linux Security;Cryptography Fundamentals;Network Security;Web Security;OWASP Top 10;Secure Coding;Authentication;Authorization;Security Testing;Ethical Hacking Fundamentals;Digital Forensics;Defensive Security;Incident Response;Vulnerability Management"),
    ("cs-fundamentals", "Computer Science Fundamentals",
     "Computer Architecture;Operating Systems;Database Management Systems;Computer Networks;Object-Oriented Programming;Software Engineering;Software Design Patterns;Compiler Fundamentals;Distributed Systems;Computer Graphics Fundamentals;Theory of Computation;System Design;Software Architecture"),
    ("game-development", "Game Development",
     "Unity;C# for Unity;Unreal Engine;Blueprints;2D Game Development;3D Game Development;Game Physics;Animation;Game AI;Multiplayer Fundamentals;Game Testing;Game Optimization;Game Publishing"),
    ("software-testing-qa", "Software Testing and QA",
     "Manual Testing;Test Case Design;Unit Testing;Integration Testing;API Testing;Selenium;Playwright;JUnit;PyTest;Performance Testing;Test Automation;Continuous Testing"),
    ("additional-paths", "Additional Learning Paths",
     "Mathematics for Programmers;Blockchain Development;Internet of Things;Embedded Systems;Robotics;UI/UX Design;Technical Interview Preparation;Portfolio Development;Open-Source Development;Freelancing Fundamentals;Competitive Programming;System Design Interview Preparation"),
]

_FIRST_CONTENT = {
    ("programming-languages", "Java"), ("programming-languages", "Python"),
    ("programming-languages", "JavaScript"), ("web-development", "HTML5"),
    ("web-development", "CSS3"), ("data-structures-algorithms", "Time Complexity"),
    ("data-structures-algorithms", "Arrays"), ("data-structures-algorithms", "Sorting Algorithms"),
}

PROJECTS = [
    "Portfolio Website", "Calculator", "To-Do Application", "Weather Application",
    "Expense Tracker", "Blog Platform", "REST API", "Student Management System",
    "Data Analysis Dashboard", "Machine Learning Prediction Model",
    "Image Classification Project", "Secure Authentication Demo",
]


def _slugify(text: str) -> str:
    text = text.lower().replace("c++", "cpp").replace("c#", "csharp")
    return re.sub(r"[^a-z0-9]+", "-", text).strip("-")


def _build():
    categories, courses, used = [], [], set()
    for cat_id, cat_name, raw in _RAW:
        titles = raw.split(";")
        n = len(titles)
        categories.append({"id": cat_id, "name": cat_name, "course_count": n})
        for i, title in enumerate(titles):
            slug = _slugify(title)
            if slug in used:
                slug = f"{slug}-{cat_id}"
            used.add(slug)
            level = "beginner" if i < n / 3 else "intermediate" if i < 2 * n / 3 else "advanced"
            status = "in_development" if (cat_id, title) in _FIRST_CONTENT else "planned"
            courses.append({"slug": slug, "title": title, "category_id": cat_id,
                            "category_name": cat_name, "level": level, "status": status})
    return categories, courses


CATEGORIES, COURSES = _build()
