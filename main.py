from re import search
import webview
from database import DatabaseController
from jinja2 import Template

current_profile = "default"

def load_html(window):
    window._js_api.goto_index()

def on_closed():
    print('webview window is closed.')
    window._js_api.db_con.close()

class Api:

    def __init__ (self):
        self.db_con = DatabaseController()
        self.last_page = 1
        self.last_search = ""
    
    def python_print(self, message):
        print(message)

    def get_lib_info (self):
        response = {
            'numFiles' : str(self.db_con.get_lib_num_files("default")),
            'size' : str(self.db_con.get_lib_size("default"))
        }
        return response
    
    def get_image_info (self, img_id):
        img_width, img_height, img_ext, img_size = self.db_con.get_file_info(
            "default", fhash=None, fid=img_id)
        response = {
            'width': img_width,
            'height': img_height,
            'extension': img_ext,
            'size': img_size
        }
        
        return response
    
    def add_tag(self, img_id, tag):
        self.db_con.add_tag_to_img("default", img_id, tag)
        response = {
            'success' : True,
            'tag' : tag
        }
        return response
    
    def remove_tag(self, img_id, tag):
        self.db_con.remove_tag_from_img("default", img_id, tag)
        


    def goto_index (self, search_form="", page=1, goto_last=False):
        file = open("templates/index.html", "r")
        index = file.read()
        file.close()
        
        current_page = page
        current_search = search_form

        if goto_last:
            current_search = self.last_search
            current_page = self.last_page

        self.last_page = current_page
        self.last_search = current_search

        results = None
        if current_search == "":
            results = self.db_con.search_query(current_profile, current_page)
        else:
            search_terms = current_search.split()
            results = self.db_con.search_query(current_profile, current_page, args=search_terms)

        images, first_page, last_page = results
        previous_search = current_search if current_search is not None else ""
        tm = Template(index)
        rend = tm.render(images=images, last_search=previous_search, current_pg=current_page, first_pg=first_page, last_pg=last_page)
        window.load_html(rend)
    
    def goto_import_prompt(self, file_path=None):
        file = open("templates/import_prompt.html", "r")
        imp = file.read()
        file.close()
        tm = Template(imp)
        rend = tm.render(file_path= file_path)
        window.load_html(rend)

    def choose_path (self, is_folder=False):
        dialog_type = webview.OPEN_DIALOG if is_folder is False else webview.FOLDER_DIALOG
        paths = webview.windows[0].create_file_dialog(dialog_type)
        path = paths[0] if paths is not None else ""
        self.import_path = path
        self.goto_import_prompt(file_path=path)

    def goto_import (self):
        print("Starting import of " + str(self.import_path))
        file = open("templates/load.html", "r")
        load = file.read()
        file.close()
        window.load_html(load)
        self.db_con.import_path(self.import_path, current_profile)
        self.goto_index()

    def goto_view (self, img_id=None, image_path=None):
        file = open("templates/view.html", "r")
        view = file.read()
        file.close()
        tm = Template(view)
        tags = self.db_con.get_img_tags(img_id)
        def_width = self.db_con.get_preferred_file_width(img_id)
        rend = tm.render(image_id=img_id, image=image_path, default_width=def_width, tags=tags)
        window.load_html(rend)


if __name__ == '__main__':
    api = Api()
    window = webview.create_window('Image Tagger', html='init',js_api=api, min_size=(880, 600), easy_drag=False, frameless=False)
    window.closed += on_closed
    webview.start(load_html, window, gui="mshtml")
