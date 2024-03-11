import os
import pickle
import random
import sqlite3
import sys
import threading
import wave

import pyaudio
import speech_recognition as sr
from playsound import playsound
from PyQt5 import QtCore, QtWidgets
from PyQt5 import uic
from PyQt5.QtCore import Qt
from PyQt5.QtWidgets import QApplication, QMainWindow, QInputDialog, QLineEdit, QPushButton, QTreeWidgetItem, \
    QListWidget, QListWidgetItem


# главный класс в котором можно:
# создавать или удалять проекты с задачами
# отследить процент их выполнения
# создавать таймер чтобы контралировать время выполнения задач
class Main(QMainWindow):
    def __init__(self):
        super().__init__()
        uic.loadUi("Project_create.ui", self)
        self.setWindowTitle("Task List")

        self.data_name = "List_of_projects.txt"
        self.projects_info = "Projects_info.txt"
        self.sound_name = "alarm.mp3"

        self.projects_class = []
        self.projects_name = []

        self.label = QtWidgets.QLabel("00:00", self)
        self.verticalLayout.addWidget(self.label)

        self.delete_button = QPushButton("Удалить проект")
        self.verticalLayout.addWidget(self.delete_button)
        self.delete_button.clicked.connect(self.delete)

        self.add_timer = QPushButton("Добавить таймер")
        self.verticalLayout.addWidget(self.add_timer)
        self.add_timer.clicked.connect(self.set_timer)

        self.scrollArea.setWidgetResizable(True)
        self.listWidget.setSelectionMode(QListWidget.SingleSelection)
        self.listWidget.itemDoubleClicked.connect(self.open_project)
        self.pushButton.clicked.connect(self.create_new_project)

        self.timer = QtCore.QTimer(self)
        self.timer.timeout.connect(self.update_timer)
        if os.path.isfile(self.data_name):
            self.load_data()

    def set_timer(self):
        dialog = TimerDialog(self)
        if dialog.exec_() == QtWidgets.QDialog.Accepted:
            self.time_left = dialog.input.value() * 60
            self.timer.start(1000)

    def update_timer(self):
        self.time_left -= 1
        minutes = self.time_left // 60
        seconds = self.time_left % 60
        self.label.setText(f'{minutes:02}:{seconds:02}')

        if self.time_left <= 0:
            self.timer.stop()
            self.play_sound()

    def play_sound(self):
        playsound(self.sound_name)

    def delete(self):
        for Item in self.listWidget.selectedItems():
            index = self.projects_name.index(Item.text().split()[0])
            self.listWidget.takeItem(self.listWidget.row(Item))
            self.projects_class.pop(index)
            self.projects_name.pop(index)
            self.clear(f"{Item.text().split()[0]}_database.db")

    def add_task(self, task):
        item = QListWidgetItem(f"{task} 0%")
        self.listWidget.addItem(item)

    def create_new_project(self):
        name, ok_pressed = QInputDialog.getText(self, "Создание нового проекта",
                                                "Название:")
        if ok_pressed:
            project = Project(name)
            self.add_task(name)
            self.projects_name.append(name)
            self.projects_class.append(project)

    # функция вызывается извне и изменяет процент на объекте item
    def update_percent(self, item, percent):
        index = self.projects_class.index(item)
        self.listWidget.item(index).setText(self.projects_name[index] + f" {percent}%")

    def open_project(self):
        for Item in self.listWidget.selectedItems():
            index = self.projects_name.index(Item.text().split()[0])
            self.projects_class[index].show()

    # сохранение списка всех проектов в файл txt
    def save_data(self):
        data = []
        for i in range(self.listWidget.count()):
            text = self.listWidget.item(i).text()
            data.append(text)
        with open(self.data_name, "wb") as f:
            pickle.dump(data, f)
        with open(self.projects_info, "wb") as file:
            pickle.dump(self.projects_class, file)
            pickle.dump(self.projects_name, file)

    # подгружает данные из файла
    def load_data(self):
        with open(self.data_name, "rb") as file:
            data = pickle.load(file)
        self.listWidget.clear()
        for text in data:
            item = QListWidgetItem(text)
            self.listWidget.addItem(item)
        with open(self.projects_info, "rb") as file:
            self.projects_class = pickle.load(file)
            self.projects_name = pickle.load(file)

    # специальная функция которая вызываетяс при нажатии на кнопку закрытия окна, сохраняет данные
    def closeEvent(self, event):
        self.save_data()
        event.accept()

    def clear(self, file):
        os.remove(file)


# класс проекта
# в нём создаются задачи, подзадачи с помощью QTreeWidget
# можно отслеживать их исполнение с помощью checkbox на каждом объекте
# каждый объект показывает насколько процентов он выполнен
#     если все дочерние объекты выполнены родитель тоже считается выполненым
#     если что то из дочерних объектов не выполнено родитель считается не выполненым
#     если родитель выполнен все дочерние объекты автоматически считаются выполеными
# также по двойному счелчку можно изменить "вес" каждой задачи
# и процент выполнения считается так (сумма всех весов выполненных дочерних объектов/сумма всех весов дочерних объектов)
# также есть взаимодействие со statusBar в котором показываются подсказки для пользователя
# также есть menuBar в котором можно:
#     закрепить окно поверх всех других
#     запретить перетаскивать окно т.е оно всегда находиться на одном месте
#     так же можно закрепить окно в спец местах:
#         вверху вправо
#         вверху влево
#         внизу  вправо
#         внизу влево
class Project(QtWidgets.QMainWindow):
    def __init__(self, name):
        super().__init__()
        uic.loadUi("tree_task.ui", self)
        self.audio_settings = {"CHUNK": 1024,
                               "FORMAT": pyaudio.paInt16,
                               "CHANNELS": 1,
                               "RATE": 44100,
                               "RECORD_SECONDS": 5,
                               "WAVE_OUTPUT_FILENAME": "voice_input.wav"}
        self.isrecording = None
        self.checkbox_change_bool = True
        self.name = name
        self.time_to_statusbar = 3000
        self.db_path = self.name + "_database.db"
        self.data_name = self.name + "_data.txt"
        self.initUI()
        self.percent_of_done = self.tree_widget.topLevelItem(0).text(0).split()[0][:-1]

    def initUI(self):
        self.setWindowTitle(self.name)

        self.statusBar = self.statusBar()

        self.tree_widget.itemDoubleClicked.connect(self.on_item_double_clicked)
        self.tree_widget.itemChanged.connect(self.checkbox_change)

        self.scrollArea.setWidgetResizable(True)

        self.add_task.clicked.connect(self.add_task_to_tree)

        self.record.pressed.connect(self.startrecording)
        self.record.released.connect(self.stoprecording)

        # не успел реализовать полностью удаление задач но можно легко добавить эту функцию
        # self.delete_task = QPushButton('Удалить задачу', self)
        # self.delete_task.move(330, 20)
        # self.delete_task.clicked.connect(self.delete_item)

        # настройка menuBar

        menubar = self.menuBar()
        fileMenu = menubar.addMenu('File')

        toggleAction = QtWidgets.QAction('Закрепить окно', self, checkable=True)
        toggleAction.setChecked(False)
        toggleAction.triggered.connect(self.change_window_state)
        fileMenu.addAction(toggleAction)

        moveAction = QtWidgets.QAction('Разрешить перемещение', self, checkable=True)
        moveAction.setChecked(True)
        moveAction.triggered.connect(self.toggle_move)
        fileMenu.addAction(moveAction)

        # создание мест для прикрепления окна

        moveMenu = menubar.addMenu('Переместить окно')
        topLeftAction = QtWidgets.QAction('В левый верхний угол', self)
        topLeftAction.triggered.connect(lambda: self.move_window('top-left'))
        moveMenu.addAction(topLeftAction)

        topRightAction = QtWidgets.QAction('В правый верхний угол', self)
        topRightAction.triggered.connect(lambda: self.move_window('top-right'))
        moveMenu.addAction(topRightAction)

        bottomLeftAction = QtWidgets.QAction('В левый нижний угол', self)
        bottomLeftAction.triggered.connect(lambda: self.move_window('bottom-left'))
        moveMenu.addAction(bottomLeftAction)

        bottomRightAction = QtWidgets.QAction('В правый нижний угол', self)
        bottomRightAction.triggered.connect(lambda: self.move_window('bottom-right'))
        moveMenu.addAction(bottomRightAction)
        self.is_movable = True
        try:
            # если в ход совершается уже не первый раз то уже имеется файл и не возникает ошибки sqlite3.OperationalError
            self.load_data()
        except sqlite3.OperationalError as e:
            # при первом входе в проект создаётся главная задачи с названием проекта это необходимо,
            # чтобы проще передавать процент выполнения всего проекта, а также корректно добавлять подзадачи
            item = QTreeWidgetItem([f"{0}% {self.name} |{50}|"])
            item.setCheckState(0, Qt.Unchecked)
            self.tree_widget.addTopLevelItem(item)

    # закрепление окна поверх других
    def change_window_state(self, state):
        if state:
            self.setWindowFlags(self.windowFlags() | QtCore.Qt.WindowStaysOnTopHint)
        else:
            self.setWindowFlags(self.windowFlags() & ~QtCore.Qt.WindowStaysOnTopHint)
        self.show()

    # функция предназначенная для перемещения окна в определённое месте
    def move_window(self, position):
        screen = QtWidgets.QDesktopWidget().screenGeometry(-1)
        window = self.geometry()
        if position == 'top-left':
            self.move(0, 0)
        elif position == 'top-right':
            self.move(screen.width() - window.width(), 0)
        elif position == 'bottom-left':
            self.move(0, screen.height() - window.height())
        elif position == 'bottom-right':
            self.move(screen.width() - window.width(), screen.height() - window.height())

    # функция для отключения рамок окна чтобы пользователь не мог его перемещать
    def toggle_move(self, state):
        if not state:
            self.setWindowFlags(self.windowFlags() | QtCore.Qt.FramelessWindowHint)
        else:
            self.setWindowFlags(self.windowFlags() & ~QtCore.Qt.FramelessWindowHint)
        self.show()

    # функция предназначенная для удаления задач (не закончено)
    def delete_item(self):
        current_item = self.tree_widget.currentItem()
        if current_item is not None:
            index = self.tree_widget.indexOfTopLevelItem(current_item)
            if index != -1:
                self.tree_widget.takeTopLevelItem(index)

    # добавление задачи в QTreeWidget
    # перед добавлением нужно обязательно выбрать объект в который добавляетя задача
    # значение записываются в виде ({процент выполнения} {название задачи} {вес задачи})
    # чтобы легко обрабатывать и легко визуально воспринималось
    def add_task_to_tree(self):
        text, okPressed = QInputDialog.getText(QLineEdit(), "Enter task name:", "New Task")
        if okPressed:
            if text != "":
                item = QTreeWidgetItem([f"{0}% {text} |{50}|"])
                item.setCheckState(0, Qt.Unchecked)
                try:
                    self.tree_widget.currentItem().addChild(item)
                    self.save_data()
                except AttributeError:
                    self.statusBar.showMessage('Выберите задачу для которой вы хотите создать подзадчу',
                                               self.time_to_statusbar)
            else:
                self.statusBar.showMessage('Введите корректное название задачи', self.time_to_statusbar)

    # функция нужна чтобы отслеживать изменение состояния чекбокса
    # в QTreeWidget нет метода которым можно отслеживать изменения состояния чекбокса
    # а есть только та которая отслеживает полностью изменение состояния объекта
    # поэтому введён флаг checkbox_change_bool чтобы случайно не вызвать функцию
    def checkbox_change(self):
        if self.checkbox_change_bool:
            for item in self.tree_widget.selectedItems():
                self.update_percent_change(item)
                self.percent_of_done = self.tree_widget.topLevelItem(0).text(0).split()[0][:-1]
                ex.update_percent(self, self.percent_of_done)

    # рекурсивное сохранение объекта вместе со всеми его дочерними
    def save_item(self, cursor, item, parent_id=None):
        checked = int(item.checkState(0) == Qt.Checked)
        percent, name, weight = item.text(0).split()
        cursor.execute("INSERT INTO tasks VALUES (?, ?, ?, ?, ?, ?)",
                       (random.randint(0, 1000), parent_id, checked, percent, name, weight))
        id = cursor.lastrowid

        for i in range(item.childCount()):
            self.save_item(cursor, item.child(i), id)

    # перезапись бд
    def save_data(self):
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()

        cursor.execute("DROP TABLE IF EXISTS tasks")
        cursor.execute("CREATE TABLE tasks "
                       "(id INTEGER PRIMARY KEY,"
                       " parent_id INT,"
                       " checked INT,"
                       " percent TEXT,"
                       " name TEXT,"
                       " weight TEXT)")
        root = self.tree_widget.invisibleRootItem()
        for i in range(root.childCount()):
            self.save_item(cursor, root.child(i))

        conn.commit()
        conn.close()

    # рекурсивная загрузка дынных из бд
    def load_items(self, cursor, parent_item=None, parent_id=None):
        if parent_id is None:
            cursor.execute(
                "SELECT id, "
                "checked, "
                "percent,"
                " name,"
                " weight FROM tasks WHERE parent_id is null")
        else:
            cursor.execute(
                "SELECT id, "
                "checked, "
                "percent,"
                " name,"
                " weight FROM tasks WHERE parent_id=?", (parent_id,))
        for id, checked, percent, name, weight in cursor.fetchall():
            item = QTreeWidgetItem([f"{percent} {name} {weight}"])
            item.setCheckState(0, Qt.Checked if checked else Qt.Unchecked)
            if parent_item is None:
                self.tree_widget.addTopLevelItem(item)
            else:
                parent_item.addChild(item)
            self.load_items(cursor, item, id)

    def load_data(self):
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        self.load_items(cursor)
        conn.close()

    # начало записи
    def startrecording(self):
        self.p = pyaudio.PyAudio()
        self.stream = self.p.open(format=self.audio_settings["FORMAT"],
                                  channels=self.audio_settings["CHANNELS"],
                                  rate=self.audio_settings["RATE"],
                                  input=True,
                                  frames_per_buffer=self.audio_settings["CHUNK"])
        self.frames = []
        self.isrecording = True
        # создание второго потока чтобы записывать аудио
        self.t = threading.Thread(target=self._record)
        self.t.run()
        self.audio_to_text()

    # окончание записи и сохранение в файл
    def stoprecording(self):
        self.isrecording = False
        self.stream.stop_stream()
        self.stream.close()
        self.p.terminate()
        wf = wave.open(self.audio_settings["WAVE_OUTPUT_FILENAME"], 'wb')
        wf.setnchannels(self.audio_settings["CHANNELS"])
        wf.setsampwidth(self.p.get_sample_size(self.audio_settings["FORMAT"]))
        wf.setframerate(self.audio_settings["RATE"])
        wf.writeframes(b''.join(self.frames))
        wf.close()

    # перевод слов из аудио в текст если не понятно что было сказано обрабатывается ошибка
    def audio_to_text(self):
        r = sr.Recognizer()
        with sr.AudioFile(self.audio_settings["WAVE_OUTPUT_FILENAME"]) as source:
            audio_data = r.record(source)
            try:
                text = r.recognize_google(audio_data, language='ru-RU')
                print(text)
            except sr.UnknownValueError:
                self.statusBar.showMessage('Извините, я не смог понять, что было сказано.', self.time_to_statusbar)

            # item = QTreeWidgetItem([f"{0}% {text} |{50}|"])
            # item.setCheckState(0, Qt.Unchecked)
            # self.tree_widget.currentItem().addChild(item)
            # self.save_data()

    # считывание данных с микрофона
    def _record(self):
        while self.isrecording:
            for i in range(0, int(self.audio_settings["RATE"] / self.audio_settings["CHUNK"] *
                                  self.audio_settings["RECORD_SECONDS"])):
                data = self.stream.read(self.audio_settings["CHUNK"])
                self.frames.append(data)

    # вычисление процента выполнения
    def update_percent_change(self, Item):
        checkState = False
        if Item.checkState(0) == Qt.Checked:
            parent = Item.parent()
            Item.setText(0, f"{100}% {' '.join(Item.text(0).split()[1:])}")
            checkState = True
        else:
            Item.setText(0, f"{0}% {' '.join(Item.text(0).split()[1:])}")
            checkState = False
        self.checkbox_change_bool = False
        self.traverse_parent(Item)
        self.traverse_child(Item, checkState)
        self.checkbox_change_bool = True

    # перебор дочерних элементов с помощью рекурсии и выставление выполненности в зависимости от checkbox родителя
    def traverse_child(self, item, checkState):
        if checkState:
            item.setCheckState(0, Qt.Checked)
            item.setText(0, f"{100}% {' '.join(item.text(0).split()[1:])}")
        else:
            item.setCheckState(0, Qt.Unchecked)
        for i in range(item.childCount()):
            child = item.child(i)
            self.traverse_child(child, checkState)

    # перебор родительских элементов и вычисление по формуле их процент выполнения
    def traverse_parent(self, item):
        all = 0
        done = 0
        parent = item.parent()
        if parent is not None:
            for i in range(parent.childCount()):
                weight = int(parent.child(i).text(0).split("|")[1])
                all += weight
                done += int(parent.child(i).text(0).split()[0][:-1]) * weight
            answer = round(done / all)
            if answer == 100:
                parent.setCheckState(0, Qt.Checked)
            else:
                parent.setCheckState(0, Qt.Unchecked)
            parent.setText(0, f"{answer}% {' '.join(parent.text(0).split()[1:])}")
            self.traverse_parent(parent)

    # изменение веса задачи
    def on_item_double_clicked(self):
        weight, ok_pressed = QInputDialog.getInt(self, "Введите вес задачи: ", "Вес")
        if ok_pressed:
            for Item in self.tree_widget.selectedItems():
                Item.setText(0, f"{Item.text(0).split('|')[0]} |{weight}|")

    # слудующие две функции нужны чтобы коректно работало сохранение каждого объекта класса Project
    # т.к сохранение происходит в классе Main с помощью модуля pickle а он не может сохранять объекты типа class

    # Как мы будем "сохранять" класс
    def __getstate__(self) -> dict:
        state = {}
        state["name"] = self.name
        return state

    # Как мы будем восстанавливать класс из байтов
    def __setstate__(self, state: dict):
        self.name = state["name"]
        self.__init__(state["name"])

    def closeEvent(self, event):
        self.save_data()
        event.accept()


# класс для создания диалогово окна для таймера
class TimerDialog(QtWidgets.QDialog):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle('Введите время')

        self.input = QtWidgets.QSpinBox(self)
        self.input.setRange(1, 60)

        self.button = QtWidgets.QPushButton('Старт', self)
        self.button.clicked.connect(self.accept)

        layout = QtWidgets.QVBoxLayout(self)
        layout.addWidget(self.input)
        layout.addWidget(self.button)


app = QApplication(sys.argv)
ex = Main()
ex.show()
sys.exit(app.exec())
