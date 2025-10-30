import imgui

def center_text(text):
    window_width = imgui.get_window_size()[0]
    text_width = imgui.calc_text_size(text)[0]

    imgui.set_cursor_pos_x((window_width - text_width) * 0.5)
    imgui.text(text)
