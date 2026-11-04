"""Original quizzes and coding challenges. Idempotent. Challenge reference solutions are checked by the tests."""
from sqlalchemy import select
from sqlalchemy.orm import Session

from .models import Challenge, Course, Question, Quiz


def Q(qtype, prompt, options, answer, explanation):
    opts = [{"id": "abcdefgh"[i], "text": t} for i, t in enumerate(options)]
    ans = [opts[i]["id"] for i in answer] if qtype != "short" else answer
    return {"qtype": qtype, "prompt": prompt, "options": opts, "answer": ans, "explanation": explanation}


QUIZZES = [
    ("python", "Python basics check", "chapter", 60, None, [
        Q("single", "What does print(2 + 3) show?", ["5", "23", "2 + 3", "An error"], [0], "Python adds the numbers first, then prints 5."),
        Q("single", "Which type is the value 249.5?", ["int", "float", "str", "bool"], [1], "A number with a decimal point is a float."),
        Q("multiple", "Which are valid Python variable names?", ["total_price", "2nd_place", "_count", "my score"], [0, 2],
          "Names cannot start with a digit or contain spaces."),
        Q("single", "What does range(1, 4) produce?", ["1, 2, 3", "1, 2, 3, 4", "0, 1, 2, 3", "2, 3, 4"], [0], "The end value is not included."),
        Q("short", "Which keyword defines a function in Python?", [], ["def"], "Functions start with def."),
    ]),
    ("python", "Python final exam", "final", 70, 20, [
        Q("single", 'What does this print? x = 7, then: if x >= 10: print("A") elif x >= 5: print("B") else: print("C")',
          ["A", "B", "C", "An error"], [1], "7 is not >= 10, but it is >= 5, so B is printed."),
        Q("single", "What does return do in a function?", ["Sends a value back to the caller", "Prints the value", "Stops Python", "Creates a variable"],
          [0], "return hands a result back to the code that called the function."),
        Q("multiple", "Which of these are loops in Python?", ["for", "while", "if", "def"], [0, 1], "if makes decisions and def defines functions."),
        Q("short", "What does len([4, 8, 15]) return? (number only)", [], ["3"], "The list has three items."),
        Q("single", "What is the result of 7 == 7.0?", ["True", "False", "An error", "7"], [0], "Python compares the numeric values, which are equal."),
        Q("single", "What does a function without a return statement give back?", ["0", "An empty string", "None", "An error"], [2],
          "Such a function returns None."),
    ]),
    ("html5", "HTML5 check", "final", 60, None, [
        Q("single", "Which tag holds the visible content of a page?", ["<head>", "<body>", "<title>", "<meta>"], [1], "Visible content goes inside body."),
        Q("single", "Which attribute gives an image a text description?", ["src", "href", "alt", "title"], [2], "alt text helps screen reader users."),
        Q("multiple", "Which tags are used to build lists?", ["<ul>", "<ol>", "<li>", "<div>"], [0, 1, 2], "ul and ol make lists, li is each item."),
    ]),
    ("css3", "CSS3 check", "final", 60, None, [
        Q("single", "Which selector targets elements with class note?", [".note", "#note", "note", "*note"], [0], "A dot selects by class."),
        Q("single", "Which box model part sits outside the border?", ["padding", "content", "margin", "outline-box"], [2], "Margin is the outer space."),
        Q("single", "Which declaration makes a parent a flex container?", ["flex: parent", "display: flex", "layout: flex", "position: flex"], [1], "Use display: flex."),
    ]),
]

CHALLENGES = [
    {"slug": "sum-of-two", "title": "Sum of two numbers", "topic": "Input and arithmetic", "difficulty": "easy",
     "statement": "Read two integers from one line and print their sum.", "input": "One line with two integers separated by a space.",
     "output": "A single integer.", "constraints": "-10^9 <= a, b <= 10^9", "starter": "# Read input with input()\n",
     "hints": ["Use input().split() to get the two parts.", "Convert each part with int()."],
     "explanation": "Split the line, convert both parts to int, add and print.",
     "ref": "a, b = map(int, input().split())\nprint(a + b)",
     "tests": [("3 4", "7", False), ("10 -2", "8", False), ("0 0", "0", True), ("1000000 2000000", "3000000", True)]},
    {"slug": "reverse-text", "title": "Reverse the text", "topic": "Strings", "difficulty": "easy",
     "statement": "Read one line of text and print it reversed.", "input": "One line of text.", "output": "The reversed line.",
     "constraints": "1 <= length <= 1000", "starter": "# Read input with input()\n",
     "hints": ["Strings support slicing.", "text[::-1] steps backwards through the string."],
     "explanation": "A slice with step -1 reverses a string.", "ref": "print(input()[::-1])",
     "tests": [("hello", "olleh", False), ("a", "a", False), ("SkillForge", "egroFllikS", True), ("racecar", "racecar", True)]},
    {"slug": "count-vowels", "title": "Count the vowels", "topic": "Strings and loops", "difficulty": "easy",
     "statement": "Read one line and print how many vowels (a, e, i, o, u, in any case) it contains.", "input": "One line of text.",
     "output": "A single integer.", "constraints": "1 <= length <= 1000", "starter": "# Read input with input()\n",
     "hints": ["Lower-case the text first.", "Loop over the characters and test membership in 'aeiou'."],
     "explanation": "Count characters that appear in the string 'aeiou' after lower-casing.",
     "ref": "print(sum(1 for c in input().lower() if c in 'aeiou'))",
     "tests": [("education", "5", False), ("rhythm", "0", False), ("AEIOU", "5", True), ("Hello World", "3", True)]},
]


def seed_assessments(db: Session) -> None:
    for slug, title, kind, pass_mark, limit, questions in QUIZZES:
        course = db.scalar(select(Course).where(Course.slug == slug))
        if course is None or db.scalar(select(Quiz.id).where(Quiz.course_id == course.id, Quiz.title == title)):
            continue
        quiz = Quiz(course_id=course.id, title=title, kind=kind, pass_mark=pass_mark, time_limit_minutes=limit, published=True)
        for i, q in enumerate(questions, 1):
            quiz.questions.append(Question(position=i, **q))
        db.add(quiz)
    for c in CHALLENGES:
        if db.scalar(select(Challenge.id).where(Challenge.slug == c["slug"])):
            continue
        db.add(Challenge(slug=c["slug"], title=c["title"], language="python", difficulty=c["difficulty"], topic=c["topic"],
                         statement_md=c["statement"], input_format=c["input"], output_format=c["output"],
                         constraints=c["constraints"], starter_code=c["starter"], hints=c["hints"], explanation=c["explanation"],
                         tests=[{"stdin": s, "expected": e, "hidden": h} for s, e, h in c["tests"]], published=True))
    db.commit()
