import base64
import sqlite3
import os
from os import path
import shutil
import hashlib
from io import BytesIO
import base64
from PIL import Image

DATABASE_LOCATION = "./db/database.db"
DEFAULT_LIBRARY_LOCATION = "./def"

ACCEPTABLE_EXTENSIONS = [".jpeg", ".jpg", ".png", ".gif"]

MAIN_SCHEMA = '''
CREATE TABLE IF NOT EXISTS profiles (id INTEGER PRIMARY KEY NOT NULL, name TEXT UNIQUE NOT NULL,  passProtected INTEGER NOT NULL, passDigest TEXT, numFiles INTEGER NOT NULL, libSize REAL NOT NULL, location TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS files (id INTEGER PRIMARY KEY NOT NULL, hash TEXT UNIQUE NOT NULL, profile INTEGER NOT NULL, extension TEXT NOT NULL, width INTEGER NOT NULL, height INTEGER NOT NULL, size INTEGER NOT NULL, FOREIGN KEY (profile) REFERENCES profiles(id));
CREATE TABLE IF NOT EXISTS tags (id INTEGER PRIMARY KEY NOT NULL, name TEXT UNIQUE NOT NULL, profile INTEGER NOT NULL, count INTEGER NOT NULL, FOREIGN KEY (profile) REFERENCES profiles(id));
CREATE TABLE IF NOT EXISTS tagMap (fileId INTEGER NOT NULL, tagId INTEGER NOT NULL, PRIMARY KEY (fileId, tagId), FOREIGN KEY (fileId) REFERENCES files(id), FOREIGN KEY (tagId) REFERENCES tags(id));
'''
suffixes = ['B', 'KB', 'MB', 'GB', 'TB', 'PB']
def readable_size (num_bytes):
    """Coverts number of bytes into a human readable format - taken from https://stackoverflow.com/questions/14996453/python-libraries-to-calculate-human-readable-filesize-from-bytes"""
    i = 0
    while num_bytes >= 1024 and i < len(suffixes)-1:
        num_bytes /= 1024
        i += 1
    f = ('%.2f' % num_bytes).rstrip('0').rstrip('.')
    return '%s %s' % (f, suffixes[i])

class DatabaseController():

    def __init__(self):
        self.db = sqlite3.connect(DATABASE_LOCATION, check_same_thread=False)
        
        # Setup the data base if it hasn't been setup already.
        for line in MAIN_SCHEMA.splitlines():
            self.db.execute(line)

        # Check if the default profile exists; if not, make it.
        profiles = self.db.execute("SELECT * FROM profiles WHERE name='default'").fetchall()
        if len(profiles) == 0:
            self.db.execute("INSERT INTO profiles (name, passProtected, passDigest, numFiles, libSize, location) VALUES ('default', 0, NULL, 0, 0.0, './library/default')")
            
            # setup the directory structure
            if not os.path.isdir("./db/library"):
                os.makedirs("./db/library")

                for i in range(0,256):
                    os.makedirs("./db/library/f" + format(i, "02x"))
                
                for i in range(0, 256):
                    os.makedirs("./db/library/t" + format(i, "02x"))
            
        self.db.commit()

    def close(self):
        self.db.close()
        print("Database closed")

    def get_profile_id(self, profile_name):
        cur = self.db.cursor()
        cur.execute("SELECT id FROM profiles WHERE name=?", (profile_name,))
        id = cur.fetchone()[0]
        cur.close()
        return id

    def get_lib_num_files(self, profile):
        cur = self.db.cursor()
        cur.execute("SELECT numFiles FROM profiles WHERE name = ?", (profile,))
        row = cur.fetchone()
        cur.close()
        return row[0]

    def get_lib_size(self, profile):
        cur = self.db.cursor()
        cur.execute("SELECT libSize FROM profiles WHERE name = ?", (profile,))
        row = cur.fetchone()
        cur.close()
        return readable_size(row[0])

    def get_file_info (self, profile, fhash=None, fid=None):
        profile_id = self.get_profile_id(profile)
        cur = self.db.cursor()

        if fid is None:
            row = cur.execute(
                "SELECT width, height, extension, size FROM files WHERE hash=? AND profile=?", (fhash, profile_id))
            width, height, ext, fsize = row.fetchone()
            ext = ext.replace(".", "")
            fsize = readable_size(fsize)
            cur.close()
            return width, height, ext, fsize
        else:
            
            row = cur.execute(
                "SELECT width, height, extension, size FROM files WHERE id=? AND profile=?", (fid, profile_id))
            width, height, ext, fsize = row.fetchone()
            ext = ext.replace(".", "")
            fsize = readable_size(fsize)
            cur.close()
            return width, height, ext, fsize
    
    def get_preferred_file_width (self, fid):
        cur = self.db.cursor()
        row = cur.execute("SELECT width FROM files WHERE id=?", (fid,))
        width = row.fetchone()[0]
        default_width = "95%" if int(width) > 1000 else width
        cur.close()
        return default_width


    def valid_file (self, fhash, fext) -> bool:
        """Returns true if the provided information matches a valid file."""
        cur = self.db.cursor()
        cur.execute("SELECT hash FROM files WHERE hash=?", (fhash, ))
        validity = True
        
        if cur.fetchone() is not None:
            validity = validity and False
        
        if fext.lower() not in ACCEPTABLE_EXTENSIONS:
            validity = validity and False
        
        cur.close()
        return validity
    
    def handle_file (self, fpath, profile_id, profile_library):
        success = True
        size_bytes = 0

        _file_name, file_ext = path.splitext(fpath)

        # get hash of image to see if its a duplicate and to have a name for the imported file.
        hasher = hashlib.md5()
        with open(fpath, "rb") as imported_f:
            buf = imported_f.read()
            hasher.update(buf)
        file_hash = str(hasher.hexdigest())
        subfolder = file_hash[:2]

        if self.valid_file(file_hash, file_ext):

            size_bytes = path.getsize(fpath)
            shutil.copy(fpath, profile_library + "f" + subfolder + "/")

            f = path.basename(fpath)

            os.rename(profile_library + "f" + subfolder + "/" + f,
                      profile_library + "f" + subfolder + "/" + file_hash + file_ext)

            img = Image.open(profile_library + "f" + subfolder + "/" + file_hash + file_ext)
            file_width, file_height = img.size
            thumb = img.copy()
            thumb.thumbnail((180,180))
            thumb.save("./db/library/t" + subfolder + "/" + file_hash + file_ext)
            thumb.close()
            img.close()
            self.db.execute("INSERT INTO files (hash, profile, extension, width, height, size) VALUES (?,?,?,?,?,?)",
                            (file_hash, profile_id, file_ext, file_width, file_height, size_bytes))
        else:
            success = False
            print("File not valid: " + file_hash + file_ext)
        
        return (success, size_bytes)   

    def import_path (self, fpath, profile_name):
        profile_library = "./db/library/"
        num_files = 0
        size_bytes = 0
        profile_id = self.get_profile_id(profile_name)
        
        if not path.isdir(fpath):
            success, size_of_file = self.handle_file(fpath, profile_id, profile_library)
            
            if success:
                num_files =  num_files + 1
                size_bytes = size_bytes + size_of_file
            else:
                print("Failed import")
                return
        else:
            for f in os.listdir(fpath):
                if path.isfile(path.join(fpath, f)):
                    success, size_of_file = self.handle_file(path.join(fpath, f), profile_id, profile_library)

                    if success:
                        num_files += 1
                        size_bytes += size_of_file
                    else:
                        print("Failed import")
            
        #update library information
        cur = self.db.cursor()
        cur.execute("UPDATE profiles SET numFiles = numFiles + ? WHERE id = ?", (num_files, profile_id,))
        current_lib_size = cur.execute("SELECT libSize FROM profiles WHERE id = ?", (profile_id,)).fetchone()[0]
        new_lib_size = current_lib_size + size_bytes
        cur.execute("UPDATE profiles SET libSize = libSize + ? WHERE id = ?", (new_lib_size, profile_id,))
        cur.close()
        self.db.commit()

    def search_query(self, profile, page, args=None):
        per_page = 45
        offset = (page-1) * per_page
        queried_files = []
        num_files = 0
        profile_id = self.get_profile_id(profile)

        cur = self.db.cursor()

        # Default index (no search, just list everything)
        if args is None:
            cur.execute("SELECT id, hash, extension FROM files WHERE profile=? ORDER BY id DESC LIMIT ? OFFSET ?;",
                        (profile_id, per_page, offset,))
            rows = cur.fetchall()
            num_files = len(rows)
            for row in rows:
                file_id, file_hash, file_ext = row
                f = file_hash + file_ext
                width, height, ext, fsize = self.get_file_info(profile, fhash=file_hash, fid=None)
                queried_files.append(
                    ["t" + file_hash[:2], f, width, height, ext, file_id, fsize])
        else:
            
            id_list = []
            #get tag ids
            for term in args:
                # try and get tag_id
                cur.execute("SELECT id FROM tags WHERE name=?", (term, ))
                row = cur.fetchall()
                if len(row) != 0:
                    id_list.append(row[0][0])
            
            if not id_list:
                return [], True, True

            # build and execute query for file ids
            query = "SELECT id FROM files"
            id_set = set(id_list)
            i = 0
            for cur_id in id_set:
                query = query + " INNER JOIN tagMap tm" + \
                        str(i) + " ON tm" + str(i) + ".fileId=files.id AND tm" + \
                        str(i) + ".tagId=" + str(cur_id)
                i += 1
            
            cur.execute(query + " ORDER BY id DESC LIMIT ? OFFSET ?;", (per_page, offset,))
           
            rows = cur.fetchall()
            num_files = len(rows)
            for row in rows:
                cur.execute("SELECT hash, extension FROM files WHERE profile=? AND id=?;", (profile_id, row[0]))
                f = cur.fetchall()[0]
                width, height, ext, fsize = self.get_file_info(profile, fhash=f[0], fid=None)
                queried_files.append(("t"+f[0][:2], f[0] + f[1], width, height, ext, row[0], fsize))

        is_first_page = True if offset == 0 else False
        is_last_page = True if num_files/per_page < 1.0 else False
        cur.close()
        return queried_files, is_first_page, is_last_page

    def add_tag_to_img (self, profile_name, img_id, tag):
        profile_id = self.get_profile_id(profile_name)
        cur = self.db.cursor()
        
        cur.execute("SELECT * FROM tags WHERE profile=? AND name=?", (profile_id, tag,))
        row = cur.fetchone()
        # Test if the tag exists already
        if row is None:
            cur.execute("INSERT INTO tags (name, profile, count) VALUES (?,?,?)", (tag, profile_id, 1,))
            tag_id = cur.execute("SELECT id FROM tags WHERE profile=? AND name=?", (profile_id, tag,)).fetchone()[0]
            cur.execute("INSERT INTO tagMap (fileID, tagID) VALUES (?,?)", (img_id, tag_id,))
        else:
            # Test if the image already has the tag assigned to it
            tag_id = cur.execute("SELECT id FROM tags WHERE profile=? AND name=?", (profile_id, tag,)).fetchone()[0]
            cur.execute("SELECT * FROM tagMap WHERE fileId=? AND tagId=?", (img_id, tag_id,))
            row = cur.fetchone()
            if row is None:
                #Update tag count
                cur.execute("UPDATE tags SET count = count + 1 WHERE profile=? AND name=?", (profile_id, tag))

                #Add tag mapping
                cur.execute("INSERT INTO tagMap (fileID, tagID) VALUES (?,?)", (img_id, tag_id,))
        cur.close()
        self.db.commit()

    def remove_tag_from_img (self, profile_name, img_id, tag):
       
        profile_id = self.get_profile_id(profile_name)
        cur = self.db.cursor()
        cur.execute("SELECT id FROM tags WHERE profile=? AND name=?", (profile_id, tag,))
        
        tag_id = cur.fetchone()[0]
        
        # remove the tag from the image.
        cur.execute("DELETE FROM tagMap WHERE fileId=? AND tagId=?", (img_id, tag_id,))

        # delete the tag if that was the last instance of it.
        results, first_pg, _last_pg = self.search_query(profile_name, 1, args=[tag])
        if len(results) == 0:
            cur.execute(
                "DELETE FROM tags WHERE profile=? AND name=?", (profile_id, tag,))

        cur.close()
        self.db.commit()
        

    def get_img_tags (self, img_id):
        tags = []
        cur = self.db.cursor()
        cur.execute("SELECT name FROM tags WHERE id IN (SELECT tagId FROM tagMap WHERE fileId=?)", (img_id,))
        rows = cur.fetchall()
        for row in rows:
            tags.append(row[0])
        cur.close()
        return tags
