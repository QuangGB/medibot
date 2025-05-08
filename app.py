from flask import Flask, render_template, request, redirect, url_for, send_from_directory
import json
from datetime import datetime
import os
import uuid
from apscheduler.schedulers.background import BackgroundScheduler
from datetime import datetime
import atexit
import requests

sent_reminders = {}
PAGE_ACCESS_TOKEN = 'EAAQT2w79fVABOZCmNdeQ67rgSC3afVw9EeIHK8r5kKfSX5sMjoyf3CGlEeFcsZBinoRZAxrRxDfCdnPXImPEQsVS38NV0OnaZCJW09CnIBbHfBdJahlOtqC5G7oryuoaSxvnsswPuvbrPbFuX5JHWrHBLU8GkkZBJZBnpKf7lvfWK0qZB7EwjgVNjZC16ZAFcsz5N6ZBYwHV4gZCk6LXQFh'
VERIFY_TOKEN = '251098'
DATA_FILE = 'medicines.json'

# ___FLASK APP___
app = Flask(__name__)

def load_data():
    """Load data from the JSON file."""
    if not os.path.exists(DATA_FILE):
        return []
    with open(DATA_FILE, 'r', encoding='utf-8') as file:
        try:
            return json.load(file)
        except json.JSONDecodeError:
            return []

def save_data(data):
    """Save data to the JSON file."""
    with open(DATA_FILE, 'w', encoding='utf-8') as file:
        json.dump(data, file, indent=4, ensure_ascii=False)

@app.route('/', methods=['GET', 'POST'])
def index():
    """Render the main page with the list of medicines."""
    if request.method == 'POST':
        # Get the form data
        name = request.form.get('name')
        time = request.form.get('time')
        messenger_id = request.form.get('messenger_id')

        # Load existing data
        data = load_data()

        # Add new medicine entry
        data.append({
            'id': str(uuid.uuid4()),  # Generate a unique ID for each entry
            'name': name,
            'time': time,
            'messenger_id': messenger_id,
            'confirmed': False,
            'remind_count': 0
        })

        # Save updated data
        save_data(data)

        return redirect(url_for('index'))
    data = load_data()
    return render_template('index.html', medicines=data)

@app.route('/favicon.ico')
def favicon():
    return send_from_directory(os.path.join(app.root_path, 'static'), 'favicon.ico', mimetype='image/vnd.microsoft.icon')

@app.route('/edit/<id>', methods=['GET', 'POST'])
def edit(id):
    """Edit a specific medicine entry."""
    data = load_data()
    medicine = next((item for item in data if item['id'] == id), None)
    if not medicine:
        return "Khong tim thay thuoc", 404  # Not found
    if request.method == 'POST':
        # Update the medicine entry
        medicine['name'] = request.form['name']
        medicine['time'] = request.form['time']
        medicine['messenger_id'] = request.form['messenger_id']

        # Save updated data
        save_data(data)
        return redirect(url_for('index'))
    return render_template('edit.html', medicine=medicine)

@app.route('/delete/<id>', methods=['POST'])
def delete(id):
    """Delete a specific medicine entry."""
    data = load_data()
    data = [item for item in data if item['id'] != id]
    save_data(data)
    return redirect(url_for('index'))

@app.route('/webhook', methods=['GET', 'POST'])
def webhook():
    """Handle incoming messages from Facebook Messenger."""
    if request.method == 'GET':
        mode = request.args.get('hub.mode')
        token = request.args.get('hub.verify_token')
        challenge = request.args.get('hub.challenge')
        if mode == 'subscribe' and token == VERIFY_TOKEN:
            print("Webhook verified")
            return challenge, 200
        else:
            print("Webhook verification failed")
            return "Verification failed", 403

    if request.method == 'POST':
        data = request.json
        print("Received data:", data)
        if data.get('object') == 'page':
            for entry in data.get('entry', []):
                for messaging_event in entry.get('messaging', []):
                    sender_id = messaging_event['sender']['id']
                    print(f"Nhận tin nhắn từ user có PSID: {sender_id}")
                    #Check if have text message
                    message_text = messaging_event.get('message', {}).get('text')
                    if message_text:
                        print(f"Nội dung tin nhắn: {message_text}")
                        msg_text = message_text.strip().lower()
                        if msg_text == 'tôi đã uống thuốc xong':
                            medicines = load_data()
                            updated = False
                            for item in medicines:
                                if item.get('messenger_id') == sender_id:
                                    item['confirmed'] = True
                                    updated = True
                            save_data(medicines)
                            send_message_messenger(sender_id, "Cảm ơn bạn đã uống thuốc. Chúc bạn mau khỏe!")
        return "OK", 200

def send_message_messenger(recipient_id, message):
    url = 'https://graph.facebook.com/v19.0/me/messages'
    headers = {'Content-Type': 'application/json'}
    data = {
        'recipient': {'id': recipient_id},
        'message': {'text': message},
        'messaging_type': 'UPDATE'
    }
    params = {'access_token': PAGE_ACCESS_TOKEN}
    response = requests.post(url, headers=headers, json=data, params=params)
    print("Messenger response:", response.json())

def check_and_send_reminders():
    now = datetime.now()
    data = load_data()
    #date_key = now.strftime('%d-%m-%Y')  # Format the date as needed
    for item in data:
        try:
            if item.get('confirmed', False):
                continue
            scheduled_time = datetime.strptime(item['time'], '%H:%M').replace(year=now.year, month=now.month, day=now.day)
            delta = (now - scheduled_time).total_seconds()
            #Neu chua den gio hoac da qua muon qua 1h thi bo qua
            if delta < 0 or delta > 3600:
                continue
            remind_count = item.get('remind_count', 0)
            if remind_count >= 10:
                continue
            unique_key = f"{item['id']}_{scheduled_time.strftime('%d-%m-%Y')}_{remind_count}"
            if unique_key not in sent_reminders and delta % 120 < 60:
                message = f"Nhắc nhở bạn uống thuốc {item['name']} vào lúc {item['time']}! Tin nhắn nhắc này sẽ lặp lại 2 phút một lần cho đến khi bạn nhắn lại với tôi rằng bạn đã uống thuốc xong."
                print(message)
                if item.get('messenger_id'):
                    send_message_messenger(item['messenger_id'], message)
                sent_reminders[unique_key] = True
                item['remind_count'] = remind_count + 1
        except ValueError:
            print(f"Time format error: {item['time']}")
    save_data(data)


scheduler = BackgroundScheduler()
scheduler.add_job(check_and_send_reminders, 'interval', minutes = 2)  # Check every 2 minutes
scheduler.start()

#Dam bao scheduler dung khi tat app
atexit.register(lambda: scheduler.shutdown())

if __name__ == '__main__':
    app.run(debug=True)
