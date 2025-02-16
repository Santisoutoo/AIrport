from PyQt6.QtCore import Qt, QTimer
from PyQt6.QtWidgets import QApplication, QWidget, QVBoxLayout, QTextEdit, QPushButton
from bluesky.network.client import Client

# Variables globales
echobox = None
cmdline = None
bsclient = None

class TextClient(Client):
    '''
    Cliente que extiende Client para revisar datos entrantes y enviar comandos.
    '''
    def __init__(self):
        super().__init__()
        self.timer = QTimer()
        self.timer.timeout.connect(self.update)
        self.timer.start(20)

    def event(self, name, data, sender_id):
        ''' Función sobrescrita para manejar los eventos entrantes. '''
        if name == b'ECHO' and echobox is not None:
            # Se envía el texto recibido al echobox.
            echobox.echo(**data)

    def stack(self, text):
        ''' Función para enviar comandos de stack a BlueSky. '''
        self.send_event(b'STACK', text)

    def echo(self, text, flags=None, **kwargs):
        ''' Sobrescribe la función echo de Client para mostrar texto en el echobox.
            Se añade **kwargs para aceptar argumentos extra (como sender_id). '''
        if echobox is not None:
            echobox.echo(text, flags)


class Echobox(QTextEdit):
    ''' Cuadro de texto para mostrar mensajes recibidos de BlueSky. '''
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setMinimumHeight(150)
        self.setReadOnly(True)

    def echo(self, text, flags=None):
        ''' Agrega el texto al cuadro de texto. '''
        self.append(text)
        self.verticalScrollBar().setValue(self.verticalScrollBar().maximum())


class Cmdline(QTextEdit):
    ''' Cuadro de texto para ingresar comandos. '''
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setMaximumHeight(21)

    def keyPressEvent(self, event):
        ''' Maneja la tecla Enter para enviar comandos a BlueSky. '''
        if event.key() in (Qt.Key.Key_Enter, Qt.Key.Key_Return):
            if bsclient is not None:
                bsclient.stack(self.toPlainText())
                echobox.echo(self.toPlainText())
            self.setText('')
        else:
            super().keyPressEvent(event)


if __name__ == '__main__':
    # Construcción de la interfaz principal
    app = QApplication([])

    # Crear ventana con un cuadro para mostrar mensajes y otro para ingresar comandos
    win = QWidget()
    win.setWindowTitle('Example external client for BlueSky')
    layout = QVBoxLayout()
    win.setLayout(layout)

    echobox = Echobox(win)
    cmdline = Cmdline(win)
    layout.addWidget(echobox)
    layout.addWidget(cmdline)
    win.show()

    # Crear y conectar el cliente BlueSky
    bsclient = TextClient()
    bsclient.connect(event_port=11000, stream_port=11001)

    # Iniciar el loop principal de Qt
    app.exec()
