import os
import sys
import subprocess
import json
import time
from datetime import datetime
import requests

class SQLmapTester:
    def __init__(self, base_url, output_dir="sqlmap_results"):
        self.base_url = base_url
        self.output_dir = output_dir
        self.results = []
        
        # Создаем папку для результатов
        os.makedirs(output_dir, exist_ok=True)
        
    def run_sqlmap(self, url, method="GET", data=None, cookies=None, headers=None, level=3, risk=2):
        """
        Запускает SQLmap с заданными параметрами
        """
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        log_file = os.path.join(self.output_dir, f"sqlmap_{timestamp}.log")
        
        # Базовые параметры SQLmap
        cmd = [
            "sqlmap",
            "-u", url,
            "--batch",  # автоматический выбор ответов
            "--level", str(level),
            "--risk", str(risk),
            "--random-agent",  # случайный User-Agent
            "--output-dir", self.output_dir,
            "--flush-session",  # очистить сессию
            "--timeout", "30"
            
        ]
        
        # Добавляем метод запроса
        if method.upper() == "POST" and data:
            cmd.extend(["--data", data])
            
        # Добавляем cookies
        if cookies:
            cookie_str = "; ".join([f"{k}={v}" for k, v in cookies.items()])
            cmd.extend(["--cookie", cookie_str])
            
        # Добавляем заголовки
        if headers:
            for key, value in headers.items():
                cmd.extend(["--header", f"{key}: {value}"])
        
        # Добавляем дополнительный параметр для тестирования формы логина
        if "login" in url or "auth" in url:
            cmd.append("--forms")  # автоматически анализирует формы
        
        print(f"\n[+] Запуск SQLmap для: {url}")
        print(f"[+] Команда: {' '.join(cmd)}")
        print(f"[+] Лог сохраняется в: {log_file}")
        
        try:
            # Запускаем SQLmap
            with open(log_file, 'w') as f:
                process = subprocess.Popen(
                    cmd,
                    stdout=subprocess.PIPE,
                    stderr=subprocess.STDOUT,
                    text=True,
                    bufsize=1
                )
                
                # Читаем вывод в реальном времени
                for line in process.stdout:
                    print(line, end='')
                    f.write(line)
                    
                process.wait()
                
            # Проверяем результат
            success = process.returncode == 0
            
            # Анализируем результат
            result = self.analyze_result(log_file)
            self.results.append({
                "url": url,
                "timestamp": timestamp,
                "success": success,
                "result": result,
                "log_file": log_file
            })
            
            return success, result
            
        except Exception as e:
            print(f"[-] Ошибка при выполнении SQLmap: {e}")
            return False, str(e)
    
    def analyze_result(self, log_file):
        """
        Анализирует вывод SQLmap для определения уязвимостей
        """
        with open(log_file, 'r') as f:
            content = f.read()
            
        analysis = {
            "vulnerable": False,
            "parameters": [],
            "techniques": [],
            "databases": [],
            "tables": [],
            "summary": ""
        }
        
        # Ищем признаки уязвимости
        if "vulnerable" in content.lower():
            analysis["vulnerable"] = True
            
            # Находим уязвимые параметры
            import re
            param_pattern = r"Parameter: (.*?) \((.*?)\)"
            params = re.findall(param_pattern, content)
            analysis["parameters"] = [p[0] for p in params]
            
            # Определяем используемые техники
            techniques = ["boolean-based blind", "error-based", "union query", "time-based blind"]
            found_techniques = [t for t in techniques if t in content.lower()]
            analysis["techniques"] = found_techniques
            
            # Находим базы данных
            db_pattern = r"\[\*\] (.*?) \[(\d+)\]"
            dbs = re.findall(db_pattern, content)
            analysis["databases"] = [db[0] for db in dbs]
            
            # Находим таблицы
            table_pattern = r"\| (.*?) \|"
            tables = re.findall(table_pattern, content)
            if tables:
                analysis["tables"] = tables[:10]  # первые 10 таблиц
            
            analysis["summary"] = "🔴 УЯЗВИМОСТЬ НАЙДЕНА!"
        else:
            analysis["summary"] = "✅ Уязвимостей не обнаружено"
            
        return analysis
    
    def test_login_form(self):
        """
        Тестирует форму входа на SQL-инъекции
        """
        print("\n" + "="*60)
        print("ТЕСТИРОВАНИЕ ФОРМЫ ВХОДА")
        print("="*60)
        
        login_url = f"{self.base_url}/login"
        
        # Пробуем разные подходы
        test_cases = [
            {
                "name": "POST форма",
                "method": "POST",
                "data": "username=admin&password=admin",
                "level": 5,
                "risk": 3
            },
            {
                "name": "С параметрами в URL",
                "method": "GET",
                "data": None,
                "level": 3,
                "risk": 2
            }
        ]
        
        results = []
        for test in test_cases:
            print(f"\n[Тест] {test['name']}")
            success, result = self.run_sqlmap(
                url=login_url,
                method=test['method'],
                data=test.get('data'),
                level=test.get('level', 3),
                risk=test.get('risk', 2)
            )
            results.append(result)
            
        return results
    
    def test_search_endpoints(self):
        """
        Тестирует поисковые эндпоинты
        """
        print("\n" + "="*60)
        print("ТЕСТИРОВАНИЕ ПОИСКОВЫХ ЭНДПОИНТОВ")
        print("="*60)
        
        endpoints = [
            "/search?q=test",
            "/students?group=ИСП-104",
            "/courses?id=1",
            "/schedule?group=123"
        ]
        
        results = []
        for endpoint in endpoints:
            url = f"{self.base_url}{endpoint}"
            print(f"\n[Тест] {endpoint}")
            
            success, result = self.run_sqlmap(
                url=url,
                method="GET",
                level=3,
                risk=2
            )
            results.append(result)
            
        return results
    
    def test_all_parameters(self):
        """
        Расширенное тестирование всех параметров
        """
        print("\n" + "="*60)
        print("РАСШИРЕННОЕ ТЕСТИРОВАНИЕ")
        print("="*60)
        
        # Собираем все параметры из URL
        import urllib.parse
        
        urls = [
            f"{self.base_url}/",
            f"{self.base_url}/map",
            f"{self.base_url}/faq",
            f"{self.base_url}/profile",
            f"{self.base_url}/admin"
        ]
        
        results = []
        for url in urls:
            print(f"\n[Тест] {url}")
            
            # Пробуем добавить тестовые параметры
            test_urls = [
                f"{url}?id=1",
                f"{url}?page=1",
                f"{url}?user=admin",
                f"{url}?group=ИСП-104"
            ]
            
            for test_url in test_urls:
                success, result = self.run_sqlmap(
                    url=test_url,
                    method="GET",
                    level=2,
                    risk=1
                )
                results.append(result)
                
        return results
    
    def generate_report(self):
        """
        Генерирует отчет о результатах тестирования
        """
        report_file = os.path.join(self.output_dir, "report.html")
        
        html = f"""
        <!DOCTYPE html>
        <html>
        <head>
            <title>SQLmap Test Report</title>
            <style>
                body {{ font-family: Arial, sans-serif; margin: 20px; }}
                .vulnerable {{ color: red; font-weight: bold; }}
                .safe {{ color: green; font-weight: bold; }}
                .summary {{ background: #f0f0f0; padding: 15px; border-radius: 5px; margin: 10px 0; }}
                table {{ border-collapse: collapse; width: 100%; }}
                th, td {{ border: 1px solid #ddd; padding: 8px; text-align: left; }}
                th {{ background-color: #4CAF50; color: white; }}
                tr:nth-child(even) {{ background-color: #f2f2f2; }}
                .timestamp {{ color: #666; font-size: 0.9em; }}
            </style>
        </head>
        <body>
            <h1>Отчет о тестировании SQL-инъекций</h1>
            <p class="timestamp">Сгенерирован: {datetime.now().strftime("%Y-%m-%d %H:%M:%S")}</p>
            <p>Целевой сайт: <strong>{self.base_url}</strong></p>
            
            <h2>Результаты тестирования</h2>
        """
        
        total_vulnerable = 0
        for i, result in enumerate(self.results, 1):
            html += f"<div class='summary'>"
            html += f"<h3>Тест #{i}</h3>"
            html += f"<p><strong>URL:</strong> {result.get('url', 'N/A')}</p>"
            html += f"<p><strong>Время:</strong> {result.get('timestamp', 'N/A')}</p>"
            
            res = result.get('result', {})
            if isinstance(res, dict):
                if res.get('vulnerable'):
                    html += f"<p class='vulnerable'>🔴 УЯЗВИМОСТЬ ОБНАРУЖЕНА!</p>"
                    total_vulnerable += 1
                    
                    if res.get('parameters'):
                        html += f"<p><strong>Уязвимые параметры:</strong> {', '.join(res['parameters'])}</p>"
                    if res.get('techniques'):
                        html += f"<p><strong>Техники:</strong> {', '.join(res['techniques'])}</p>"
                    if res.get('databases'):
                        html += f"<p><strong>Найденные БД:</strong> {', '.join(res['databases'][:5])}</p>"
                else:
                    html += f"<p class='safe'>✅ Уязвимостей не обнаружено</p>"
            
            html += f"<p><strong>Лог:</strong> <a href='{result.get('log_file', '')}'>{result.get('log_file', 'N/A')}</a></p>"
            html += "</div>"
        
        html += f"""
            <h2>Итоговое резюме</h2>
            <div class='summary'>
                <p><strong>Всего тестов:</strong> {len(self.results)}</p>
                <p><strong>Найдено уязвимостей:</strong> {total_vulnerable}</p>
                <p><strong>Статус:</strong> {
                    "🔴 САЙТ УЯЗВИМ ДЛЯ SQL-ИНЪЕКЦИЙ!" if total_vulnerable > 0 else "✅ Сайт защищен от SQL-инъекций"
                }</p>
            </div>
        </body>
        </html>
        """
        
        with open(report_file, 'w', encoding='utf-8') as f:
            f.write(html)
            
        print(f"\n[+] Отчет сохранен: {report_file}")
        return report_file

def main():
    """
    Основная функция запуска тестирования
    """
    print("="*60)
    print("SQL INJECTION TESTER v1.0")
    print("="*60)
    
    # Настройка
    base_url = "https://student.pir0g.ru"  # URL вашего приложения
    tester = SQLmapTester(base_url)
    
    # Проверяем установку SQLmap
    try:
        subprocess.run(["sqlmap", "--version"], capture_output=True, check=True)
        print("[+] SQLmap найден")
    except:
        print("[-] SQLmap не найден. Установите: pip install sqlmap")
        print("Или скачайте с: https://sqlmap.org/")
        return
    
    print(f"\n[+] Начинаем тестирование {base_url}")
    print("[!] Это может занять много времени...")
    
    try:
        # Запускаем все тесты
        tester.test_login_form()
        tester.test_search_endpoints()
        tester.test_all_parameters()
        
        # Генерируем отчет
        report = tester.generate_report()
        
        print(f"\n[+] Тестирование завершено!")
        print(f"[+] Отчет доступен по пути: {report}")
        
        # Выводим краткий итог
        total_vulnerable = sum(1 for r in tester.results if r.get('result', {}).get('vulnerable', False))
        if total_vulnerable > 0:
            print(f"\n[!] НАЙДЕНО {total_vulnerable} УЯЗВИМОСТЕЙ!")
            print("[!] НЕОБХОДИМО ПРИНЯТЬ МЕРЫ ЗАЩИТЫ!")
        else:
            print(f"\n[+] Уязвимостей не найдено. Сайт защищен!")
            
    except KeyboardInterrupt:
        print("\n[-] Тестирование прервано пользователем")
    except Exception as e:
        print(f"[-] Ошибка: {e}")

if __name__ == "__main__":
    main()