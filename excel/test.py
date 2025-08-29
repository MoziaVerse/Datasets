import pytest
import time
import json
import os
import csv
import requests
from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.common.exceptions import TimeoutException, NoSuchElementException

class TestExcelAutomation:
    def setup_method(self, method):
        self.driver = webdriver.Chrome()
        self.vars = {}
        # 初始化CSV文件相关属性
        self.csv_file = None
        self.csv_writer = None
        self.session = requests.Session()  # 用于保持会话状态

    def teardown_method(self, method):
        # 关闭CSV文件
        if self.csv_file:
            self.csv_file.close()
        self.driver.quit()

    def initialize_csv(self, file_name):
        """
        初始化CSV文件用于实时记录
        """
        csv_file_path = f"chat_history_{file_name}.csv"
        self.csv_file = open(csv_file_path, "w", newline="", encoding="utf-8")
        fieldnames = ["id", "role", "content", "timestamp", "file_name", "expected_answer"]
        self.csv_writer = csv.DictWriter(self.csv_file, fieldnames=fieldnames)
        self.csv_writer.writeheader()
        print(f">>> 初始化CSV文件: {csv_file_path}")

    def write_to_csv(self, message_data):
        """
        实时写入消息到CSV文件
        """
        if self.csv_writer:
            self.csv_writer.writerow(message_data)
            self.csv_file.flush()  # 立即刷新到磁盘
            print(f">>> 实时记录消息到CSV: {message_data.get('id', 'N/A')}")

    def get_chat_history(self, chat_id, retries=3, delay=5):
        """
        通过API获取聊天记录，带重试机制
        """
        # 从浏览器中获取access_token
        access_token = self.driver.execute_script("return window.localStorage.getItem('access_token');")

        if not access_token:
            print(">>> 无法从localStorage获取access_token")
            return None

        headers = {
            'Authorization': f'Bearer {access_token}'
        }

        api_url = f"http://localhost:8002/history/message?uuid={chat_id}"
        for attempt in range(retries):
            try:
                print(f">>> 尝试获取聊天记录 (尝试 {attempt + 1}/{retries})")
                response = self.session.get(api_url, headers=headers)
                if response.status_code == 200:
                    chat_data = response.json()
                    print(f">>> 获取到的聊天数据: {json.dumps(chat_data, indent=2, ensure_ascii=False)}")

                    # 检查是否有消息内容
                    if chat_data and "messages" in chat_data and len(chat_data["messages"]) > 0:
                        messages = chat_data["messages"]
                        print(f">>> 消息数量: {len(messages)}")

                        # 检查消息内容
                        for i, msg in enumerate(messages):
                            print(f">>> 消息 {i}: {json.dumps(msg, indent=2, ensure_ascii=False)}")

                        return chat_data
                    else:
                        print(f">>> 聊天记录为空或没有消息内容")
                elif response.status_code == 401:
                    print(f"认证失败，状态码: {response.status_code}")
                else:
                    print(f"获取聊天记录失败，状态码: {response.status_code}")

            except Exception as e:
                print(f"请求聊天记录时出错: {e}")

            if attempt < retries - 1:  # 不是最后一次尝试
                print(f">>> 等待 {delay} 秒后重试...")
                time.sleep(delay)

        return None

    def test_excel_automation(self):
        try:
            print(">>> 步骤1: 打开网页并登录...")
            self.driver.get("http://localhost:5173/")
            # 设置页面加载超时
            self.driver.set_page_load_timeout(30)

            # 增加全局等待时间，确保页面有足够时间加载
            wait = WebDriverWait(self.driver, 30, poll_frequency=1)  

            # 点击登录按钮
            wait.until(EC.element_to_be_clickable((By.CSS_SELECTOR, ".h-10"))).click()

            # 输入账号和密码
            wait.until(
                EC.visibility_of_element_located((By.CSS_SELECTOR, ".space-y-2:nth-child(1) > .w-full"))
            ).send_keys("")  # 输入相应的账号
            wait.until(
                EC.visibility_of_element_located((By.CSS_SELECTOR, ".space-y-2:nth-child(2) > .w-full"))
            ).send_keys("")  # 输入相应的密码

            # 点击登录确认按钮
            wait.until(EC.element_to_be_clickable((By.CSS_SELECTOR, ".bg-black"))).click()
            time.sleep(10)  

            # 读取JSON文件中的数据集
            json_file_path = ""    # 替换为实际的JSON文件路径
            if not os.path.exists(json_file_path):
                raise FileNotFoundError(f"JSON文件未找到：{json_file_path}")

            with open(json_file_path, "r", encoding="utf-8") as f:
                data = json.load(f)

            # 按文件名分组数据，以便处理连续问题
            grouped_data = {}
            for item in data:
                file_name = item["file_name"]
                if file_name not in grouped_data:
                    grouped_data[file_name] = []
                grouped_data[file_name].append(item)

            previous_file_name = None

            for file_name, questions in grouped_data.items():
                chat_id = None
                if file_name != previous_file_name:
                    print(f"\n>>> 正在处理新文件: {file_name}")
                    # 初始化CSV文件用于实时记录
                    self.initialize_csv(file_name)

                    # 点击数据分析按钮，开启新对话
                    print(">>> 步骤2: 点击数据分析按钮，开启新对话...")
                    time.sleep(2)
                    button = self.driver.find_element(By.CSS_SELECTOR, ".btn:nth-child(3)")
                    button.click()
                    print(">>> 数据分析按钮已点击。")

                    # 关键步骤：等待页面跳转并加载数据分析页面
                    print(">>> 正在等待数据分析页面加载完成...")
                    wait.until(EC.presence_of_element_located((By.CSS_SELECTOR, ".bg-base-100.p-5")))
                    print(">>> 数据分析页面已加载。")
                    time.sleep(5) 

                    # 上传文件
                    print(">>> 步骤3: 正在上传文件...")
                    file_path = os.path.join("", file_name)    # 替换为实际的Excel文件路径
                    if not os.path.exists(file_path):
                        raise FileNotFoundError(f"Excel文件未找到：{file_path}")

                    # 直接定位隐藏的input元素并发送文件路径
                    file_input = self.driver.find_element(By.ID, "appendixUploadFile")
                    file_input.send_keys(file_path)
                    print(f">>> 文件 {file_name} 已上传。")
                    time.sleep(5)

                    # 发送初始提问 ("帮我分析一份数据")
                    print(">>> 步骤4: 发送初始问题：'帮我分析这份数据'")
                    try:
                        chat_input = wait.until(
                            EC.visibility_of_element_located(
                                (By.CSS_SELECTOR, '[data-placeholder="WriteWise让创作更加简单..."]')
                            )
                        )
                    except TimeoutException:
                        # 如果找不到带占位符的输入框，尝试找普通的输入框
                        chat_input = wait.until(
                            EC.visibility_of_element_located(
                                (By.CSS_SELECTOR, 'textarea')
                            )
                        )
                    chat_input.send_keys("帮我分析这份数据")
                    time.sleep(3)

                    send_button = wait.until(EC.element_to_be_clickable((By.CSS_SELECTOR, ".flex > .btn-circle")))
                    send_button.click()
                    print(">>> 初始问题已发送。")
                    time.sleep(5)

                    # 等待SVG元素出现
                    try:
                        svg_element = wait.until(EC.presence_of_element_located((By.CSS_SELECTOR, "svg[xmlns='http://www.w3.org/2000/svg']")))
                        print(">>> SVG元素已出现。")

                        # 等待SVG元素消失
                        try:
                            wait.until(EC.staleness_of(svg_element))
                            print(">>> SVG元素已消失。")
                        except TimeoutException:
                            print(">>> 警告: SVG元素在规定时间内未消失，继续执行后续步骤。")
                            time.sleep(10)  # 额外等待10秒
                    except TimeoutException:
                        print(">>> 警告: 未检测到SVG元素，继续执行后续步骤。")
                        time.sleep(10)

                    # 获取聊天ID
                    current_url = self.driver.current_url
                    chat_id = current_url.split('/chat/')[-1]
                    print(f">>> 当前聊天ID: {chat_id}")

                else:
                    print(f"\n>>> 正在当前对话中发送问题 (文件: {file_name})")

                # 遍历并发送JSON中的所有问题
                for item in questions:
                    # 在每个问题后加上 "/no_think"
                    question = item["question"] + " /no_think"
                    # 获取期望答案
                    expected_answer = item.get("answer", "")

                    print(f">>> 步骤5: 发送问题: {question}")
                    try:
                        chat_input = wait.until(
                            EC.visibility_of_element_located(
                                (By.CSS_SELECTOR, '[data-placeholder="WriteWise让创作更加简单..."]')
                            )
                        )
                    except TimeoutException:
                        # 如果找不到带占位符的输入框，尝试找普通的输入框
                        chat_input = wait.until(
                            EC.visibility_of_element_located(
                                (By.CSS_SELECTOR, 'textarea')
                            )
                        )
                    chat_input.send_keys(question)
                    time.sleep(3)

                    send_button = wait.until(EC.element_to_be_clickable((By.CSS_SELECTOR, ".flex > .btn-circle")))
                    send_button.click()
                    print(">>> 问题已发送。")

                    # 等待SVG元素出现
                    try:
                        svg_element = wait.until(EC.presence_of_element_located((By.CSS_SELECTOR, "svg[xmlns='http://www.w3.org/2000/svg']")))
                        print(">>> SVG元素已出现。")

                        # 等待SVG元素消失后，延迟5秒再发送下一个问题
                        try:
                            wait.until(EC.staleness_of(svg_element))
                            print(">>> SVG元素已消失。")
                            time.sleep(5)  # 等待5秒后再发送下一个问题
                        except TimeoutException:
                            print(">>> 警告: SVG元素在规定时间内未消失，继续执行后续步骤。")
                            time.sleep(5)  # 额外等待5秒
                    except TimeoutException:
                        print(">>> 警告: 未检测到SVG元素，继续执行后续步骤。")
                        time.sleep(5)

                    # 实时获取并记录最新的AI回复
                    if chat_id:
                        print(f">>> 实时获取最新的AI回复...")
                        # 增加额外等待时间确保AI回复完成
                        time.sleep(5)
                        chat_history = self.get_chat_history(chat_id, retries=3, delay=5)
                        if chat_history and "messages" in chat_history:
                            messages = chat_history["messages"]

                            # 获取最新的AI回复（至少要有2条消息，跳过第一条初始问题）
                            if len(messages) >= 2:
                                latest_message = messages[-1]  # 最新消息
                                print(f">>> 最新消息: {json.dumps(latest_message, indent=2, ensure_ascii=False)}")

                                # 记录AI的回复（支持多种角色）
                                if isinstance(latest_message, dict):
                                    message_role = latest_message.get("source", latest_message.get("role", ""))
                                    # 检查是否为AI回复角色
                                    if message_role in ["assistant", "excel_analyze_agent"]:
                                        message_record = {
                                            "id": latest_message.get("id", f"msg_{int(time.time())}"),
                                            "role": message_role,
                                            "content": str(latest_message.get("content", "")),
                                            "timestamp": latest_message.get("created_at", time.strftime("%Y-%m-%d %H:%M:%S")),
                                            "file_name": file_name,
                                            "expected_answer": expected_answer
                                        }
                                        self.write_to_csv(message_record)
                                    else:
                                        print(f">>> 最新消息不是AI回复，角色为: {message_role}")
                                else:
                                    print(">>> 最新消息格式不正确")
                            else:
                                print(">>> 消息数量不足，至少需要2条消息")
                        else:
                            print(">>> 获取聊天记录失败或数据格式不正确")

                previous_file_name = file_name

            print("\n>>> 所有文件处理和问题发送已完成。")
            time.sleep(10)

        except Exception as e:
            print(f"测试过程中发生了一个错误: {e}")
            # 尝试重新获取driver状态
            try:
                title = self.driver.title
                print(f"当前页面标题: {title}")
            except:
                print("浏览器窗口已关闭或不可用")
            self.driver.quit()
            pytest.fail(f"测试失败: {e}")