from flask import Flask, render_template, request, redirect, session, send_file
import csv
from datetime import datetime
import os
import pandas as pd
from io import BytesIO

app = Flask(__name__)
app.secret_key = 'supersecretkey'

# Инициализация файлов данных
def init_files():
    # Создаем файл reagents.csv, если он не существует
    if not os.path.exists('reagents.csv'):
        with open('reagents.csv', 'w', newline='', encoding='utf-8') as f:
            writer = csv.writer(f)
            writer.writerow(['Название', 'Количество'])  # Заголовки для reagents.csv
    
    # Создаем файл log.csv, если он не существует
    if not os.path.exists('log.csv'):
        with open('log.csv', 'w', newline='', encoding='utf-8') as f:
            writer = csv.writer(f)
            writer.writerow(['Время', 'Пользователь', 'Действие', 'Название', 'Количество'])  # Заголовки для log.csv

def read_reagents():
    with open('reagents.csv', 'r', encoding='utf-8') as f:
        reader = csv.DictReader(f)
        return list(reader)

def write_reagents(data):
    with open('reagents.csv', 'w', newline='', encoding='utf-8') as f:
        writer = csv.DictWriter(f, fieldnames=['Название', 'Количество'])
        writer.writeheader()
        writer.writerows(data)

def log_action(action, reagent, amount):
    with open('log.csv', 'a', newline='', encoding='utf-8') as f:
        writer = csv.writer(f)
        writer.writerow([
            datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
            session.get('role'),
            action,
            reagent,
            amount
        ])

@app.route('/', methods=['GET', 'POST'])
def login():
    init_files()
    error = None
    if request.method == 'POST':
        username = request.form['username']
        password = request.form['password']
        
        if username == 'admin' and password == 'admin':
            session['role'] = 'admin'
            return redirect('/admin')
        elif username == 'user' and password == 'user':
            session['role'] = 'user'
            return redirect('/user')
        else:
            error = 'Неверные учетные данные'
    return render_template('login.html', error=error)

@app.route('/admin', methods=['GET', 'POST'])
def admin_panel():
    if session.get('role') != 'admin':
        return redirect('/')
    
    error = None
    reagents = read_reagents()  # Читаем список реагентов
    
    if request.method == 'POST':
        reagent = request.form['reagent'].strip()
        amount = request.form['amount']
        
        if not reagent or not amount.isdigit():
            error = 'Некорректные данные'
        else:
            found = False
            for item in reagents:
                if item['Название'] == reagent:
                    item['Количество'] = str(int(item['Количество']) + int(amount))
                    found = True
                    break
            if not found:
                reagents.append({'Название': reagent, 'Количество': amount})
            
            write_reagents(reagents)
            log_action('Добавление', reagent, amount)
            return redirect('/admin')
    
    # Передаем список реагентов в шаблон
    return render_template('admin.html', reagents=reagents, error=error)

@app.route('/user', methods=['GET', 'POST'])
def user_panel():
    if session.get('role') != 'user':
        return redirect('/')
    
    error = None
    reagents = read_reagents()
    
    if request.method == 'POST':
        reagent_name = request.form['reagent']
        amount = request.form['amount']
        
        if not reagent_name or not amount.isdigit():
            error = 'Некорректные данные'
        else:
            amount = int(amount)
            for item in reagents:
                if item['Название'] == reagent_name:
                    current = int(item['Количество'])
                    if current < amount:
                        error = 'Недостаточно на складе'
                    else:
                        item['Количество'] = str(current - amount)
                        write_reagents(reagents)
                        log_action('Списание', reagent_name, amount)
                        return redirect('/user')
            error = 'Реактив не найден'
    
    return render_template('user.html', reagents=reagents, error=error)

@app.route('/logout')
def logout():
    session.clear()
    return redirect('/')

@app.route('/download/reagents')
def download_reagents():
    if session.get('role') != 'admin':
        return redirect('/')
    
    df = pd.read_csv('reagents.csv', encoding='utf-8')
    output = BytesIO()
    with pd.ExcelWriter(output, engine='openpyxl') as writer:
        df.to_excel(writer, index=False)
    output.seek(0)
    
    return send_file(
        output,
        download_name='reagents.xlsx',
        as_attachment=True,
        mimetype='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet'
    )

@app.route('/download/log')
def download_log():
    if session.get('role') != 'admin':
        return redirect('/')
    
    # Проверяем, существует ли файл log.csv
    if not os.path.exists('log.csv'):
        init_files()  # Создаем файл с правильной структурой
    
    # Читаем данные
    try:
        log_df = pd.read_csv('log.csv', encoding='utf-8')
        
        # Проверяем, есть ли столбец 'Действие'
        if 'Действие' not in log_df.columns:
            raise KeyError('Столбец "Действие" отсутствует в log.csv')
        
        # Сортируем и группируем
        log_df['Действие'] = pd.Categorical(log_df['Действие'], ['Добавление', 'Списание'])
        log_df = log_df.sort_values(['Название', 'Действие', 'Время'])
        
        # Создаем структуру для отчета
        report = []
        current_reagent = None
        
        for reagent in log_df['Название'].unique():
            # Добавляем разделитель между разными реагентами
            if current_reagent is not None:
                report.append({} | {col: '' for col in log_df.columns})
            
            # Фильтруем записи по реагенту
            reagent_logs = log_df[log_df['Название'] == reagent]
            report.extend(reagent_logs.to_dict('records'))
            
            # Добавляем строку с остатком
            current_amount = next((r['Количество'] for r in read_reagents() if r['Название'] == reagent), 0)
            report.append({
                'Время': 'Остаток на складе:',
                'Пользователь': '',
                'Действие': '',
                'Название': reagent,
                'Количество': current_amount
            })
            current_reagent = reagent
        
        # Формируем итоговый DataFrame
        report_df = pd.DataFrame(report)
        
        # Создаем файл
        output = BytesIO()
        with pd.ExcelWriter(output, engine='openpyxl') as writer:
            report_df.to_excel(writer, index=False)
        output.seek(0)
        
        return send_file(
            output,
            download_name='log_report.xlsx',
            as_attachment=True,
            mimetype='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet'
        )
    
    except KeyError as e:
        # Если столбец отсутствует, создаем новый файл
        init_files()
        return "Файл log.csv был поврежден. Создан новый файл. Попробуйте еще раз.", 400
    except Exception as e:
        return f"Произошла ошибка: {str(e)}", 500

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000)