import os
import sys
import requests

def process_directory(directory="./to_upload"):
    if not os.path.isdir(directory):
        print(f"Ошибка: Директория '{directory}' не найдена!")
        sys.exit(1)

    url = "http://10.1.5.233:5002/glmocr/parse"

    # Перебираем все элементы в директории
    for filename in os.listdir(directory):
        file_path = os.path.join(directory, filename)
        
        # Пропускаем папки, работаем только с файлами
        if os.path.isfile(file_path):
            print(f"Отправка файла: {file_path}")
            
            try:
                # Открываем файл и отправляем запрос
                with open(file_path, 'rb') as file_data:
                    files = {'file': file_data}
                    data = {'return_base64': 'true'}
                    
                    response = requests.post(url, files=files, data=data)
                    
                    print(f"Статус-код: {response.status_code}")
                    # Раскомментируйте, чтобы выводить ответ сервера полнее:
                    # print(f"Ответ: {response.text[:200]}...") 
                    
            except Exception as e:
                print(f"Ошибка при отправке файла {filename}: {e}")
                
            print("-" * 50)

if __name__ == "__main__":
    target_dir = sys.argv[1] if len(sys.argv) > 1 else "./to_upload"
    for i in range(2):
        process_directory(target_dir)
