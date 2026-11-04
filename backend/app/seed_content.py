"""Original starter curriculum. Seeding is idempotent: a course that already exists is left untouched,
so edits and student progress are never overwritten. Python examples are executed by the test suite
and compared with the expected output shown to students."""
from sqlalchemy import select
from sqlalchemy.orm import Session

from .catalog import COURSES
from .models import Course, Lesson, Module


def L(slug, title, body, code, lang, out=""):
    return {"slug": slug, "title": title, "body": body.strip(), "code": code.strip(), "lang": lang, "out": out.strip()}


CONTENT = [
    {
        "slug": "python",
        "summary": "Write your first Python programs: printing, variables, decisions, loops and functions.",
        "objectives": ["Print text and calculated values", "Store data in variables of different types",
                       "Make decisions with if, elif and else", "Repeat work with for and while loops",
                       "Package logic into reusable functions"],
        "est_minutes": 75,
        "modules": [
            {"title": "Getting started", "lessons": [
                L("first-program", "Your first program: print()", """
Every program starts by doing something you can see. In Python, `print()` shows text on the screen.

## Key ideas
- A **string** is text inside quotes, such as `"Hello"`.
- A **variable** is a name that stores a value, such as `name = "Asha"`.
- `print()` shows one or more values, separated by spaces.

## Line by line
1. `name = "Asha"` stores the text Asha in the variable `name`.
2. `print("Hello, " + name + "!")` joins three strings with `+` and prints the result.
3. `print("2 + 3 =", 2 + 3)` prints the text, then the number 5 that Python calculates.

## Where it is used
Scripts print progress messages, results and error details so people can see what happened.

## Common mistakes
- A missing closing quote causes a `SyntaxError`.
- Python is case sensitive: `Print` does not work, `print` does.
- Joining text and a number with `+` (for example `"Age: " + 12`) raises a `TypeError`. Use a comma instead: `print("Age:", 12)`.

## Practice
Change `name` to your own name, then add a third line that prints your favourite number multiplied by 4.
""", """
name = "Asha"
print("Hello, " + name + "!")
print("2 + 3 =", 2 + 3)
""", "python", """
Hello, Asha!
2 + 3 = 5
"""),
                L("variables-types", "Variables and data types", """
A variable gives a name to a value. Python decides the value's **type** from what you store.

## Key ideas
- `int` is a whole number, such as `3`.
- `float` is a number with a decimal point, such as `249.5`.
- `bool` is `True` or `False`.
- `str` is text.
- A comparison such as `total > 500` produces a `bool`.

## Line by line
1. `price` holds a float and `quantity` holds an int.
2. `total = price * quantity` multiplies them: 249.5 x 3 = 748.5.
3. `is_big_order = total > 500` is `True` because 748.5 is greater than 500.
4. `type(x).__name__` gives the name of the type, which is useful when debugging.

## Where it is used
Prices, counts, flags and names in every real application are stored in variables.

## Common mistakes
- Using a name before assigning it causes a `NameError`.
- Names cannot start with a digit or contain spaces. Use `total_price`, not `total price`.
- `=` assigns a value. `==` compares two values.

## Practice
Add a `discount = 0.1` variable and print the total after the discount.
""", """
price = 249.5
quantity = 3
total = price * quantity
is_big_order = total > 500
print(type(price).__name__, type(quantity).__name__, type(is_big_order).__name__)
print("Total:", total)
print("Big order?", is_big_order)
""", "python", """
float int bool
Total: 748.5
Big order? True
"""),
                L("if-else", "Making decisions with if", """
Programs choose what to do based on conditions. Python checks them from top to bottom and runs the first block whose condition is true.

## Key ideas
- `if` starts a decision; `elif` adds another test; `else` runs when nothing above matched.
- Each block is **indented** (four spaces is the convention) after a line ending with a colon.
- Comparison operators include `>`, `>=`, `<`, `<=`, `==` and `!=`.

## Line by line
1. `score = 72` stores the mark.
2. `72 >= 90` is false, so the first block is skipped.
3. `72 >= 70` is true, so `grade` becomes `"B"` and the remaining branches are skipped.
4. `print("Grade:", grade)` runs after the whole decision.

## Where it is used
Login checks, discounts, validation and game rules all rely on conditions.

## Common mistakes
- Forgetting the colon at the end of the `if` line causes a `SyntaxError`.
- Wrong indentation causes an `IndentationError` or changes what the program does.
- Order matters: testing `score >= 70` before `score >= 90` would give a B to a score of 95.

## Practice
Add a grade `"D"` for scores below 50, and test your program with scores 95, 72, 60 and 30.
""", """
score = 72
if score >= 90:
    grade = "A"
elif score >= 70:
    grade = "B"
else:
    grade = "C"
print("Grade:", grade)
""", "python", "Grade: B"),
            ]},
            {"title": "Repeating and organizing", "lessons": [
                L("loops", "Repeating work with loops", """
A loop repeats a block of code so you do not have to write it many times.

## Key ideas
- `for n in range(1, 6)` repeats for 1, 2, 3, 4 and 5. The end value 6 is **not** included.
- `while condition:` repeats as long as the condition stays true.
- `total += n` is shorthand for `total = total + n`.

## Line by line
1. The `for` loop adds each number from 1 to 5 to `total`, giving 15.
2. The `while` loop starts with `count = 3`, prints it, then reduces it by 1.
3. When `count` reaches 0 the condition `count > 0` is false and the loop ends.

## Where it is used
Processing every row in a file, every item in a cart, or retrying a network request.

## Common mistakes
- A `while` loop that never changes its condition runs forever (an infinite loop). Press Ctrl+C to stop it.
- Off-by-one errors: `range(1, 5)` stops at 4.

## Practice
Use a loop to print the first five multiples of 7.
""", """
total = 0
for n in range(1, 6):
    total += n
print("Sum:", total)

count = 3
while count > 0:
    print("Countdown", count)
    count -= 1
""", "python", """
Sum: 15
Countdown 3
Countdown 2
Countdown 1
"""),
                L("functions", "Reusable code with functions", """
A function is a named block of code you can run whenever you need it, with different inputs each time.

## Key ideas
- `def name(parameters):` defines a function.
- `return` sends a result back to the caller.
- A **parameter** is the name inside the definition; an **argument** is the value you pass in.

## Line by line
1. `average(numbers)` adds the numbers with `sum()` and divides by how many there are with `len()`.
2. `average(marks)` receives `[80, 90, 70]` and returns 80.0.
3. `round(value, 1)` rounds to one decimal place, so 87.5 stays 87.5.

## Where it is used
Every larger program is built from functions, which makes code shorter, testable and easier to fix.

## Common mistakes
- Calling a function before it is defined raises a `NameError`.
- Forgetting `return` makes the function give back `None`.
- Dividing by `len()` of an empty list raises `ZeroDivisionError`.

## Practice
Write `maximum(numbers)` that returns the largest value without using the built-in `max()`.
""", """
def average(numbers):
    return sum(numbers) / len(numbers)

marks = [80, 90, 70]
print("Average:", average(marks))
print("Rounded:", round(average([85, 90]), 1))
""", "python", """
Average: 80.0
Rounded: 87.5
"""),
            ]},
        ],
    },
    {
        "slug": "html5",
        "summary": "Build and structure a web page with HTML: document structure, text, links, lists and images.",
        "objectives": ["Describe the structure of an HTML document", "Mark up headings, paragraphs and links",
                       "Create lists and add accessible images"],
        "est_minutes": 45,
        "modules": [{"title": "HTML basics", "lessons": [
            L("page-structure", "The structure of an HTML page", """
HTML describes the meaning and structure of a page using **elements** written as tags.

## Key ideas
- `<!DOCTYPE html>` tells the browser to use modern HTML.
- `<html lang="en">` wraps the page and states its language.
- `<head>` holds information about the page, such as its `<title>`. `<body>` holds what people see.

## What you will see
A page with a large heading, "Hello, web", and a paragraph below it. The browser tab shows "My first page".

## Common mistakes
- Forgetting a closing tag, such as `</p>`, can change the layout of everything after it.
- Putting visible content in `<head>` instead of `<body>`.

## Practice
Save the code as `index.html`, open it in a browser, then change the heading text and refresh.
""", """
<!DOCTYPE html>
<html lang="en">
  <head>
    <meta charset="UTF-8" />
    <title>My first page</title>
  </head>
  <body>
    <h1>Hello, web</h1>
    <p>This is my first page.</p>
  </body>
</html>
""", "html"),
            L("text-and-links", "Headings, paragraphs and links", """
Text is organized with headings and paragraphs, and pages are connected with links.

## Key ideas
- `<h1>` to `<h6>` are headings. Use one `<h1>` per page and keep the order logical.
- `<p>` is a paragraph.
- `<a href="...">` makes a link. The `href` attribute holds the destination.

## What you will see
A heading, a paragraph with a bold word, and a link that opens another page when clicked.

## Common mistakes
- Choosing a heading level for its size instead of its meaning. Change size with CSS instead.
- Link text such as "click here" is unclear. Describe the destination instead.

## Practice
Add a second link that points to a page you create, `about.html`.
""", """
<h1>Learning to code</h1>
<p>Practice <strong>a little every day</strong> and your skills will grow.</p>
<p>Read more on <a href="https://developer.mozilla.org/">MDN Web Docs</a>.</p>
""", "html"),
            L("lists-and-images", "Lists and images", """
Lists group related items, and images make pages richer. Both need to work for people using screen readers.

## Key ideas
- `<ul>` is an unordered (bulleted) list, `<ol>` is ordered (numbered). Each item is an `<li>`.
- `<img src="..." alt="...">` shows an image. The `alt` text describes it for people who cannot see it.

## What you will see
A numbered list of three steps. The image appears only if a file named `logo.png` sits next to your page; otherwise the browser shows the alt text.

## Common mistakes
- Leaving out `alt`, or writing "image" as the alt text.
- Placing text directly inside `<ul>` without `<li>`.

## Practice
Turn a list of your three favourite foods into a `<ul>`.
""", """
<ol>
  <li>Write the HTML</li>
  <li>Open it in a browser</li>
  <li>Fix and repeat</li>
</ol>
<img src="logo.png" alt="SkillForge logo" width="120" />
""", "html"),
        ]}],
    },
    {
        "slug": "css3",
        "summary": "Style web pages with CSS: selectors, colours, the box model and Flexbox layout.",
        "objectives": ["Select elements and set their style properties", "Explain content, padding, border and margin",
                       "Arrange items in a row or column with Flexbox"],
        "est_minutes": 45,
        "modules": [{"title": "CSS basics", "lessons": [
            L("selectors", "Selectors and properties", """
CSS changes how HTML looks. A rule has a **selector** (what to style) and **declarations** (how to style it).

## Key ideas
- An element selector such as `p` targets every paragraph.
- A class selector such as `.note` targets elements with `class="note"`.
- A declaration is `property: value;`, such as `color: teal;`.

## What you will see
Normal paragraphs in teal text, and the paragraph with the class `note` shown in bold on a pale yellow background.

## Common mistakes
- A missing semicolon or brace can cancel the rest of the rule.
- When two rules conflict, the more specific selector wins, so `.note` beats `p`.

## Practice
Make all headings dark blue and give `.note` a left border.
""", """
<style>
  p { color: teal; }
  .note { font-weight: bold; background: #fff8c5; }
</style>
<p>A normal paragraph.</p>
<p class="note">An important note.</p>
""", "html"),
            L("box-model", "The box model", """
Every element is a box made of four layers: **content**, **padding**, **border** and **margin**.

## Key ideas
- Padding is space inside the border; margin is space outside it.
- `box-sizing: border-box` makes `width` include padding and border, which is easier to plan with.

## What you will see
A 200 pixel wide card with a dark border, comfortable space inside, and 20 pixels of space around it.

## Common mistakes
- Forgetting that padding adds to the width when `box-sizing` is not set.
- Vertical margins between neighbouring blocks can collapse into one.

## Practice
Increase the padding to 24px and check how the card changes.
""", """
<style>
  .card {
    box-sizing: border-box;
    width: 200px;
    padding: 16px;
    border: 2px solid #12202e;
    margin: 20px;
  }
</style>
<div class="card">A card with padding, border and margin.</div>
""", "html"),
            L("flexbox", "Layout with Flexbox", """
Flexbox arranges items in a row or a column and controls spacing and alignment.

## Key ideas
- `display: flex` on a parent turns its children into flex items.
- `justify-content` spreads items along the main axis; `align-items` aligns them across it.
- `gap` sets the space between items.

## What you will see
Three coloured boxes in one row, evenly spaced. Narrow your window and use `flex-wrap: wrap` to let them move to a new line.

## Common mistakes
- Setting `display: flex` on the child instead of the parent.
- Forgetting that `flex-direction: column` swaps the roles of the two axes.

## Practice
Change `justify-content` to `center`, then to `space-between`, and compare.
""", """
<style>
  .row { display: flex; justify-content: space-around; gap: 12px; }
  .box { padding: 16px; background: #0b6b5e; color: white; }
</style>
<div class="row">
  <div class="box">One</div>
  <div class="box">Two</div>
  <div class="box">Three</div>
</div>
""", "html"),
        ]}],
    },
]


def seed_content(db: Session) -> None:
    for c in CONTENT:
        if db.scalar(select(Course.id).where(Course.slug == c["slug"])):
            continue
        base = next(x for x in COURSES if x["slug"] == c["slug"])
        course = Course(slug=c["slug"], title=base["title"], category_id=base["category_id"], level=base["level"],
                        summary=c["summary"], objectives=c["objectives"], est_minutes=c["est_minutes"], published=True)
        for mi, m in enumerate(c["modules"], 1):
            module = Module(title=m["title"], position=mi)
            for li, l in enumerate(m["lessons"], 1):
                module.lessons.append(Lesson(slug=l["slug"], title=l["title"], position=li, body_md=l["body"],
                                             example_code=l["code"], example_lang=l["lang"],
                                             expected_output=l["out"], published=True))
            course.modules.append(module)
        db.add(course)
    db.commit()
