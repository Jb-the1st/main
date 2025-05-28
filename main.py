from flask import Flask, render_template, request, redirect, url_for, session, jsonify, flash
from functools import wraps
from flask_mysqldb import MySQL
from MySQLdb.cursors import DictCursor
# from flask_bcrypt import Bcrypt
import random
import os
import csv

app = Flask(__name__)
app.secret_key = "b@0J98!xZq#P$T2&k7rM"
# bcrypt = Bcrypt(app)
# MySQL Configuration
development = False  # Set to True for local development, False for production
if development:
    # Local database config
    app.config['MYSQL_HOST'] = 'localhost'
    app.config['MYSQL_USER'] = 'root'
    app.config['MYSQL_PASSWORD'] = ''
    app.config['MYSQL_DB'] = 'flask_auth'
    app.config["MYSQL_CURSORCLASS"] = "DictCursor"
else:
    # Production database config
    app.config["MYSQL_HOST"] = "b8gqfahoe4si97cggnha-mysql.services.clever-cloud.com"
    app.config["MYSQL_USER"] = "uementg4xw74zkj3"
    app.config["MYSQL_PASSWORD"] = "Ggkg1ynqrIk7hvIuMRti"
    app.config["MYSQL_DB"] = "b8gqfahoe4si97cggnha"
    app.config["MYSQL_CURSORCLASS"] = "DictCursor"

mysql = MySQL(app)

# Load questions from CSV file
def load_questions(subject_id=None):
    questions = []
    try:
        if subject_id:
            filename = f"questions_{subject_id}.csv"
        else:
            filename = "questions.csv"
            
        with open(filename, newline="", encoding="utf-8") as csvfile:
            reader = csv.DictReader(csvfile)
            for row in reader:
                questions.append(row)
    except FileNotFoundError:
        print(f"Error: {filename} not found!")
    return questions

# Login required decorator for users
def login_required(f):
    @wraps(f)
    def wrap(*args, **kwargs):
        if "username" not in session:
            flash("You need to log in first!", "danger")
            return redirect(url_for("login"))
        return f(*args, **kwargs)
    return wrap

# Login required decorator for admin
def admin_required(f):
    @wraps(f)
    def wrap(*args, **kwargs):
        if "admin" not in session:
            flash("Admin access required!", "danger")
            return redirect(url_for("admin_login"))
        return f(*args, **kwargs)
    return wrap

@app.route("/")
def index():
    return redirect(url_for("login"))
    
@app.route("/login", methods=["GET", "POST"])
def login():
    if request.method == "POST":
        username = request.form["username"]
        password = request.form["password"]
        subject_id = request.form.get("subject_id")

        cur = mysql.connection.cursor()
        cur.execute("SELECT * FROM users WHERE username = %s AND password = %s", (username, password))
        user = cur.fetchone()

        if user:
            session["username"] = username

            if subject_id:
                print(f"Setting subject_id to: {subject_id}")
                cur.execute("SELECT subject_name, is_active FROM subjects WHERE id = %s", (subject_id,))
                subject = cur.fetchone()

                if subject:
                    if subject["is_active"] == 0:
                        flash("This subject is currently disabled", "error")
                        cur.close()
                        return redirect(url_for('login'))

                    session["subject_id"] = subject_id
                    session["subject_name"] = subject["subject_name"]

                    # Check if the user has taken the exam
                    cur.execute("SELECT score FROM scores WHERE username = %s AND subject_id = %s", (username, subject_id))
                    result = cur.fetchone()

                    if result:
                        session["has_taken_exam"] = True
                        session["score"] = result["score"]
                    else:
                        session["has_taken_exam"] = False
                        session["score"] = 0
                        session["question_index"] = 0

                        subject_questions = load_questions(subject_id)
                        if not subject_questions:
                            flash("No questions available for this subject", "error")
                            cur.close()
                            return render_template("login.html", subjects=manage_subjects())

                        question_indices = list(range(len(subject_questions)))
                        random.shuffle(question_indices)
                        session["question_indices"] = question_indices
                        session["user_answers"] = {str(i): "" for i in range(len(subject_questions))}

                    cur.close()
                    return redirect(url_for("home"))
                else:
                    flash("Invalid subject selected", "error")
                    cur.close()
                    return redirect(url_for("login"))

            flash("Please select a valid subject", "error")
            cur.close()
        else:
            flash("Invalid username or password", "error")

    # GET method: show login page
    cur = mysql.connection.cursor()
    cur.execute("SELECT * FROM subjects")
    subjects = cur.fetchall()
    cur.close()

    return render_template("login.html", subjects=subjects)

@app.route("/admin/register", methods=["GET", "POST"])
@admin_required
def register():
    if request.method == "POST":
        username = request.form["username"]
        password = request.form["password"]
        cur = mysql.connection.cursor()
        try:
            cur.execute("INSERT INTO users (username, password) VALUES (%s, %s)", (username, password))
            mysql.connection.commit()
            flash("Registration successful! New user has been added.", "success")
            return redirect(url_for("admin_dashboard"))
        except Exception as e:
            flash("Username is already in use", "error")
        finally:
            cur.close()
    return render_template("register.html")

@app.route("/logout")
def logout():
    session.clear()
    return redirect(url_for("login"))

@app.route("/home")
@login_required
def home():
    # Check if user has already taken the exam
    if session.get("has_taken_exam", False):
        return render_template(
            "home.html",
            username=session.get("username"),
            subject_name=session.get("subject_name"),
            has_taken_exam=True,
            score=session.get("score", 0)
        )
    else:
        # Initialize or get question data for the test
        subject_id = session.get("subject_id")
        subject_questions = load_questions(subject_id)
        total_questions = len(subject_questions)
        
        # Continue with the exam
        return render_template(
            "home.html",
            username=session.get("username"),
            subject_name=session.get("subject_name"),
            has_taken_exam=False,
            score=session.get("score", 0),
            total_questions=total_questions
        )

@app.route("/get_question/<int:question_num>")
@login_required
def get_question(question_num):
    subject_id = session.get("subject_id")
    if not subject_id:
        return jsonify({"error": "Subject not found in session"}), 400

    cursor = mysql.connection.cursor()
    cursor.execute("SELECT * FROM subjects WHERE id = %s", (subject_id,))
    subject = cursor.fetchone()
    
    if not subject or subject['is_active'] == 0:
        return jsonify({"error": "This subject is currently disabled"}), 403

    # Check if user has already taken the exam
    if session.get("has_taken_exam", True):
        return jsonify({
            "message": f"Test for {session.get('subject_name', 'Unknown')} already completed", 
            "score": session.get("score", 0), 
            "total_questions": len(load_questions(subject_id))
        })

    # Get subject questions
    subject_questions = load_questions(subject_id)
    question_indices = session.get("question_indices", list(range(len(subject_questions))))
    
    if question_num >= len(subject_questions) or question_num < 0:
        return jsonify({"error": "Invalid question number"}), 400

    session["question_index"] = question_num
    actual_question_index = question_indices[question_num]
    q = subject_questions[actual_question_index]

    user_answers = session.get("user_answers", {})
    previous_answer = user_answers.get(str(question_num), "")

    return jsonify({
        "question": q["question"],
        "option_a": q["option_a"],
        "option_b": q["option_b"],
        "option_c": q["option_c"],
        "option_d": q["option_d"],
        "current_answer": previous_answer,
        "question_number": question_num
    })

@app.route("/view_result")
@login_required
def view_result():
    username = session["username"]

    cur = mysql.connection.cursor()
    cur.execute("""
        SELECT sb.subject_name, s.score
        FROM scores s
        JOIN subjects sb ON s.subject_id = sb.id
        WHERE s.username = %s
    """, (username,))
    
    results = cur.fetchall()
    cur.close()

    if not results:
        return "No results found", 404

    return render_template("result.html", username=username, results=results)
@app.route("/save_answer", methods=["POST"])
@login_required
def save_answer():
    if request.is_json:
        question_num = request.json.get("question_num")
        answer = request.json.get("answer", "")
        
        # Get user answers dictionary
        user_answers = session.get("user_answers", {})
        
        # Debug print
        print(f"Saving answer for question {question_num}: {answer}")
        
        # Save this answer
        user_answers[str(question_num)] = answer
        
        # Update session
        session["user_answers"] = user_answers
        print(f"Updated user_answers in session: {user_answers}")
        
        return jsonify({"success": True})
    
    return jsonify({"error": "Invalid request"}), 400

@app.route("/get_all_answers")
@login_required
def get_all_answers():
    subject_id = session.get("subject_id")
    subject_questions = load_questions(subject_id)
    user_answers = session.get("user_answers", {})
    
    return jsonify({
        "total_questions": len(subject_questions),
        "answers": user_answers
    })

@app.route("/submit_test", methods=["POST"])
@login_required
def submit_test():
    username = session["username"]
    subject_id = session.get("subject_id")
    
    # Check if user has already taken this exam
    cur = mysql.connection.cursor()
    cur.execute("SELECT * FROM scores WHERE username = %s AND subject_id = %s", 
                (username, subject_id))
    existing_score = cur.fetchone()
    
    if existing_score:
        cur.close()
        return jsonify({
            "error": "You have already taken this test",
            "score": existing_score["score"],
            "already_taken": True
        }), 403
    
    # Calculate score
    subject_questions = load_questions(subject_id)
    question_indices = session.get("question_indices", list(range(len(subject_questions))))
    user_answers = session.get("user_answers", {})
    
    correct_count = 0
    total_questions = len(subject_questions)
    
    # Debug print
    print(f"User answers: {user_answers}")
    print(f"Question indices: {question_indices}")
    
    for question_num_str, user_answer in user_answers.items():
        if user_answer:  # If answer is not empty
            question_num = int(question_num_str)
            # Convert from single letter (a,b,c,d) to option_format
            user_option = f"option_{user_answer}".lower()
            
            # Make sure the question_num is within range
            if question_num >= 0 and question_num < len(question_indices):
                # Get the actual question index from the randomized indices
                actual_question_index = question_indices[question_num]
                correct_option = subject_questions[actual_question_index]["answer"].lower()
                
                print(f"Q{question_num}: User answered '{user_option}', correct is '{correct_option}'")
                
                if user_option == correct_option:
                    correct_count += 1
    
    # Calculate percentage score
    if total_questions > 0:
        final_score = round((correct_count / total_questions) * 100)
    else:
        final_score = 0
    
    print(f"Final score: {final_score}% ({correct_count}/{total_questions})")
    
    # Save final score to the database
    try:
        cur.execute(
            "INSERT INTO scores (username, score, subject_id) VALUES (%s, %s, %s)",
            (username, final_score, subject_id)
        )
        mysql.connection.commit()
    except Exception as e:
        print(f"Database error: {str(e)}")
        cur.close()
        return jsonify({"error": str(e)}), 500
    finally:
        cur.close()
    
    # Mark exam as completed
    session["has_taken_exam"] = True
    session["score"] = final_score
    
    return jsonify({
        "message": "Test Completed",
        "score": final_score,
        "total_questions": total_questions,
        "correct_answers": correct_count
    })
# Admin Login Route
@app.route("/admin_login", methods=["GET", "POST"])
def admin_login():
    if request.method == "POST":
        username = request.form["username"]
        password = request.form["password"]
        cur = mysql.connection.cursor()
        cur.execute("SELECT * FROM admin WHERE username = %s AND password = %s", (username, password))
        admin = cur.fetchone()
        cur.close()
        if admin:
            session["admin"] = username
            return redirect(url_for("admin_dashboard"))
        else:
            flash("Invalid admin credentials!")
    return render_template("admin_login.html")

# Admin Dashboard Route
@app.route("/admin_dashboard")
@admin_required
def admin_dashboard():
    page = request.args.get("page", 1, type=int)  # Get current page, default is 1
    per_page = 5  # Number of users per page
    offset = (page - 1) * per_page  # Calculate offset

    cur = mysql.connection.cursor()
    cur.execute("SELECT COUNT(*) AS total FROM users")  # Get total user count
    total_users = cur.fetchone()["total"]
    
    cur.execute("SELECT * FROM users LIMIT %s OFFSET %s", (per_page, offset))  # Fetch paginated users
    users = cur.fetchall()

    cur.execute("SELECT * FROM scores")  # Fetch all scores
    scores = cur.fetchall()
    
    cur.close()

    total_pages = (total_users // per_page) + (1 if total_users % per_page > 0 else 0)  # Calculate total pages

    return render_template("admin_dashboard.html", users=users, scores=scores, page=page, total_pages=total_pages)

@app.route("/delete_user/<int:user_id>")
@admin_required
def delete_user(user_id):
    cur = mysql.connection.cursor()
    cur.execute("DELETE FROM users WHERE id = %s", (user_id,))
    cur.execute("DELETE FROM scores WHERE username = (SELECT username FROM users WHERE id = %s)", (user_id,))
    mysql.connection.commit()
    cur.close()
    flash("User deleted successfully!", "success")
    return redirect(url_for("admin_dashboard"))

# Update User
@app.route("/update_user/<int:user_id>", methods=["POST"])
@admin_required
def update_user(user_id):
    username = request.form["username"]
    password = request.form["password"]
    cur = mysql.connection.cursor()
    cur.execute("UPDATE users SET username = %s, password = %s WHERE id = %s", (username, password, user_id))
    mysql.connection.commit()
    cur.close()
    flash("User updated successfully!", "success")
    return redirect(url_for("admin_dashboard"))

# Search Users
@app.route("/search_users", methods=["POST"])
@admin_required
def search_users():
    search_query = request.form["search"]
    page = request.args.get("page", 1, type=int)
    per_page = 5
    offset = (page - 1) * per_page

    cur = mysql.connection.cursor()
    cur.execute("SELECT COUNT(*) AS total FROM users WHERE username LIKE %s", ("%" + search_query + "%",))
    total_users = cur.fetchone()["total"]

    cur.execute("SELECT * FROM users WHERE username LIKE %s LIMIT %s OFFSET %s", 
                ("%" + search_query + "%", per_page, offset))
    users = cur.fetchall()

    cur.execute("SELECT * FROM scores")
    scores = cur.fetchall()
    
    cur.close()

    total_pages = (total_users // per_page) + (1 if total_users % per_page > 0 else 0)

    return render_template("admin_dashboard.html", users=users, scores=scores, page=page, total_pages=total_pages, search_query=search_query)

# Admin Routes for Subject Management
@app.route("/admin/subjects", methods=["GET", "POST"])
@admin_required
def manage_subjects():
    if request.method == "POST":
        if request.form.get("subject_name"):
            subject_name = request.form.get("subject_name")
            cur = mysql.connection.cursor()
            cur.execute("INSERT INTO subjects (subject_name) VALUES (%s)", (subject_name,))
            mysql.connection.commit()
            cur.close()
            flash("Subject added successfully!", "success")
        elif request.form.get("subject_id") and request.form.get("action"):
            subject_id = request.form.get("subject_id")
            action = request.form.get("action")
            cur = mysql.connection.cursor()
            if action == "enable":
                cur.execute("UPDATE subjects SET is_active = 1 WHERE id = %s", (subject_id,))
            elif action == "disable":
                cur.execute("UPDATE subjects SET is_active = 0 WHERE id = %s", (subject_id,))
            mysql.connection.commit()
            cur.close()
            flash("Subject updated successfully!", "success")

    # Get all subjects
    cur = mysql.connection.cursor()
    cur.execute("SELECT * FROM subjects")
    subjects = cur.fetchall()
    cur.close()

    return render_template("admin_subjects.html", subjects=subjects)
@app.route("/admin/subjects/delete/<int:subject_id>")
@admin_required
def delete_subject(subject_id):
    cur = mysql.connection.cursor()
    # First delete related scores
    cur.execute("DELETE FROM scores WHERE subject_id = %s", (subject_id,))
    # Then delete the subject
    cur.execute("DELETE FROM subjects WHERE id = %s", (subject_id,))
    mysql.connection.commit()
    cur.close()
    flash("Subject deleted successfully!", "success")
    return redirect(url_for("manage_subjects"))

# Question Management Routes
@app.route("/admin/questions/<int:subject_id>", methods=["GET"])
@admin_required
def view_questions(subject_id):
    # Get subject name
    cur = mysql.connection.cursor()
    cur.execute("SELECT subject_name FROM subjects WHERE id = %s", (subject_id,))
    subject = cur.fetchone()
    cur.close()
    
    if not subject:
        flash("Subject not found!", "error")
        return redirect(url_for("manage_subjects"))
    
    # Load questions for this subject from CSV
    questions = []
    try:
        filename = f"questions_{subject_id}.csv"
        if os.path.exists(filename):
            with open(filename, newline="", encoding="utf-8") as csvfile:
                reader = csv.DictReader(csvfile)
                questions = list(reader)
    except Exception as e:
        flash(f"Error loading questions: {str(e)}", "error")
    
    return render_template("admin_questions.html", 
                          subject=subject, 
                          questions=questions, 
                          subject_id=subject_id)

@app.route("/admin/questions/upload/<int:subject_id>", methods=["POST"])
@admin_required
def upload_questions(subject_id):
    if 'question_file' not in request.files:
        flash("No file part", "error")
        return redirect(url_for("view_questions", subject_id=subject_id))
    
    file = request.files['question_file']
    if file.filename == '':
        flash("No selected file", "error")
        return redirect(url_for("view_questions", subject_id=subject_id))
    
    if file and file.filename.endswith('.csv'):
        try:
            # Save uploaded file
            filename = f"questions_{subject_id}.csv"
            file.save(filename)
            
            # Verify CSV format
            with open(filename, newline='', encoding='utf-8') as csvfile:
                reader = csv.DictReader(csvfile)
                # Check if required fields exist
                required_fields = ['question', 'option_a', 'option_b', 'option_c', 'option_d', 'answer']
                first_row = next(reader, None)
                if first_row is None:
                    flash("CSV file is empty", "error")
                    return redirect(url_for("view_questions", subject_id=subject_id))
                
                missing_fields = [field for field in required_fields if field not in first_row]
                if missing_fields:
                    flash(f"CSV missing required fields: {', '.join(missing_fields)}", "error")
                    return redirect(url_for("view_questions", subject_id=subject_id))
            
            flash("Questions uploaded successfully!", "success")
        except Exception as e:
            flash(f"Error processing file: {str(e)}", "error")
    else:
        flash("Only CSV files are allowed", "error")
    
    return redirect(url_for("view_questions", subject_id=subject_id))
@app.route("/admin/analytics")
@admin_required
def admin_analytics():
    cur = mysql.connection.cursor(DictCursor)

    # Query to get scores grouped by subject
    cur.execute("""
        SELECT
            s.id AS subject_id,
            s.subject_name AS subject_name,
            COUNT(sc.id) AS total_attempts,
            COUNT(DISTINCT sc.username) AS total_users,
            AVG(sc.score) AS average_score,
            MAX(sc.score) AS highest_score,
            MIN(sc.score) AS lowest_score,
            STDDEV(sc.score) AS score_deviation
        FROM subjects s
        LEFT JOIN scores sc ON s.id = sc.subject_id
        GROUP BY s.id, s.subject_name
        ORDER BY s.subject_name
    """)

    subjects_data = cur.fetchall()

    # Get distribution data for score ranges
    cur.execute("""
        SELECT
            s.id AS subject_id,
            s.subject_name AS subject_name,
            CASE
                WHEN sc.score < 40 THEN '0-39'
                WHEN sc.score < 60 THEN '40-59'
                WHEN sc.score < 75 THEN '60-74'
                WHEN sc.score < 90 THEN '75-89'
                ELSE '90-100'
            END AS score_range,
            COUNT(sc.id) AS count
        FROM subjects s
        JOIN scores sc ON s.id = sc.subject_id
        GROUP BY s.id, s.subject_name, score_range
        ORDER BY s.subject_name, score_range
    """)

    distribution_data = cur.fetchall()

    cur.close()

    # Process data for charts
    subjects = []
    avg_scores = []
    user_counts = []
    distribution_chart_data = {}

    for subject in subjects_data:
        subjects.append(subject['subject_name'])
        avg_scores.append(float(subject['average_score']) if subject['average_score'] is not None else 0)
        user_counts.append(subject['total_users'] or 0)

    for item in distribution_data:
        subject_name = item['subject_name']
        if subject_name not in distribution_chart_data:
            distribution_chart_data[subject_name] = {'ranges': [], 'counts': []}
        
        distribution_chart_data[subject_name]['ranges'].append(item['score_range'])
        distribution_chart_data[subject_name]['counts'].append(item['count'])

    # Optional: if no analytics data exists at all, redirect or show message
    if not any(avg_scores):
        flash("No analytics data available yet. No scores have been recorded.", "info")
        return redirect(url_for("admin_dashboard"))

    return render_template(
        "admin_analytics.html",
        subjects_data=subjects_data,
        subjects=subjects,
        avg_scores=avg_scores,
        user_counts=user_counts,
        distribution_chart_data=distribution_chart_data
    )


@app.route("/admin/questions/add/<int:subject_id>", methods=["POST"])
@admin_required
def add_question(subject_id):
    question = request.form.get("question")
    option_a = request.form.get("option_a")
    option_b = request.form.get("option_b")
    option_c = request.form.get("option_c")
    option_d = request.form.get("option_d")
    answer = request.form.get("answer")
    
    if not all([question, option_a, option_b, option_c, option_d, answer]):
        flash("All fields are required", "error")
        return redirect(url_for("view_questions", subject_id=subject_id))
    
    filename = f"questions_{subject_id}.csv"
    file_exists = os.path.exists(filename)
    
    try:
        with open(filename, 'a', newline='', encoding='utf-8') as csvfile:
            fieldnames = ['question', 'option_a', 'option_b', 'option_c', 'option_d', 'answer']
            writer = csv.DictWriter(csvfile, fieldnames=fieldnames)
            
            if not file_exists:
                writer.writeheader()
            
            writer.writerow({
                'question': question,
                'option_a': option_a,
                'option_b': option_b,
                'option_c': option_c,
                'option_d': option_d,
                'answer': answer
            })
        
        flash("Question added successfully!", "success")
    except Exception as e:
        flash(f"Error adding question: {str(e)}", "error")
    
    return redirect(url_for("view_questions", subject_id=subject_id))

# Admin Logout Route
@app.route("/admin_logout")
def admin_logout():
    session.pop("admin", None)
    return redirect(url_for("admin_login"))

if __name__ == "__main__":
    app.run(debug=True)