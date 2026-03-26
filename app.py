from flask import Flask, render_template, request, redirect, url_for

app = Flask(__name__)

todos = []

@app.route('/')
def index():
    return render_template('index.html', todos=todos)

@app.route('/add', methods=['POST'])
def add():
    task = request.form.get('task')
    if task:
        todos.append({'task': task, 'done': False})
    return redirect(url_for('index'))

@app.route('/delete/<int:index>')
def delete(index):
    todos.pop(index)
    return redirect(url_for('index'))

@app.route('/complete/<int:index>')
def complete(index):
    todos[index]['done'] = not todos[index]['done']
    return redirect(url_for('index'))

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000)