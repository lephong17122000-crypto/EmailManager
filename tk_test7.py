# =================== YouTube Channel Manager ===================
import tkinter as tk
from tkinter import ttk, messagebox, filedialog, simpledialog
import json, os, time, threading, base64, io, shutil
import pyotp, pyperclip, requests
from bs4 import BeautifulSoup
import ctypes
from tkinter import font as tkfont
# Using hazmat for low-level crypto ops (PBKDF2)
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.kdf.pbkdf2 import PBKDF2HMAC
# Using Fernet for symmetric encryption
from cryptography.fernet import Fernet
# Import InvalidToken directly from the fernet module
from cryptography.fernet import InvalidToken
# Using regex for validation
import re
import openpyxl
from openpyxl.utils import get_column_letter


# Import Pillow and pyzbar, handling potential import errors
try:
    from PIL import Image, ImageTk # ImageTk for Tkinter compatibility
    import pyzbar.pyzbar as pyzbar
    HAS_QR_LIBS = True
except ImportError:
    # Use try-except for messagebox as root might not be fully available yet
    try:
        messagebox.showwarning("Thiếu Thư Viện", "Không tìm thấy thư viện Pillow và pyzbar. Chức năng quét mã QR sẽ bị vô hiệu hóa.\nCài đặt bằng lệnh:\npip install Pillow pyzbar")
    except Exception:
         print("Cảnh báo: Không tìm thấy thư viện Pillow và pyzbar. Chức năng QR bị tắt.")
    HAS_QR_LIBS = False

# Constants
FILE = "channels.json"
ENCRYPTED_FERNET_KEY_FILE = "encrypted_fernet.key"
SALT_FILE = "salt.key"
BACKUP_DIR = "backups"
# Thời gian chờ tự động khóa (ví dụ: 15 phút = 900000 ms). Đặt None để tắt
AUTO_LOCK_TIMEOUT_MS = None # 900000

# -------- Master Password Dialog ---------
class MasterPasswordDialog(tk.Toplevel):
    """Hộp thoại Mật khẩu Master để xác thực và thiết lập ban đầu."""

    def __init__(self, parent, first_time=False):
        super().__init__(parent)
        self.parent = parent
        self.first_time = first_time
        self.result = None
        self.title("Thiết lập Mật khẩu Master" if first_time else "Yêu cầu Mật khẩu Master")
        self.resizable(False, False)
        self.transient(parent) # Làm cho cửa sổ này luôn ở trên cửa sổ cha
        self.grab_set() # Biến cửa sổ này thành modal (chặn tương tác với cửa sổ khác)
        self.protocol("WM_DELETE_WINDOW", self.on_cancel) # Xử lý sự kiện đóng cửa sổ

        self._build_ui() # Xây dựng giao diện người dùng của hộp thoại
        self._center_window() # Căn giữa hộp thoại trên cửa sổ cha (root)

        # Thêm topmost và focus force để đảm bảo hộp thoại luôn ở trên cùng và có focus khi mở
        self.attributes('-topmost', True)
        self.focus_force()
        # Loại bỏ topmost sau một thời gian ngắn để cho phép các cửa sổ khác nổi lên sau đó
        # Sau khi grab_set, topmost không quá cần thiết, nhưng giữ lại để đảm bảo.
        # self.after(50, lambda: self.attributes('-topmost', False)) # Có thể gây vấn đề trên một số hệ thống

    def _center_window(self):
        """Căn giữa cửa sổ hộp thoại so với cửa sổ cha."""
        # Báo cáo lỗi nếu parent không tồn tại hoặc bị hủy
        if not self.parent or not self.parent.winfo_exists():
             print("Cảnh báo: Không thể căn giữa hộp thoại, cửa sổ cha không tồn tại.")
             return # Không thể căn giữa nếu không có cửa sổ cha

        self.update_idletasks() # Đảm bảo các widget được đo và kích thước cửa sổ được tính toán

        # Lấy kích thước yêu cầu của cửa sổ dựa trên nội dung
        width = self.winfo_reqwidth()
        height = self.winfo_reqheight()

        # Lấy vị trí và kích thước của cửa sổ cha (root)
        # window.winfo_x(), window.winfo_y() lấy tọa độ góc trên bên trái của cửa sổ so với màn hình
        parent_x = self.parent.winfo_x()
        parent_y = self.parent.winfo_y()
        parent_width = self.parent.winfo_width()
        parent_height = self.parent.winfo_height()

        # Tính toán vị trí để căn giữa hộp thoại trên cửa sổ cha
        x = parent_x + (parent_width // 2) - (width // 2)
        y = parent_y + (parent_height // 2) - (height // 2)

        # Đặt hình học (kích thước và vị trí) cho cửa sổ hộp thoại
        self.geometry(f"{width}x{height}+{x}+{y}")

        # Tùy chọn: Đặt kích thước tối thiểu để ngăn cửa sổ bị thu nhỏ quá mức nội dung
        self.minsize(width, height)


    def _build_ui(self):
        pad = 10
        frame = ttk.Frame(self, padding=pad)
        frame.grid(row=0, column=0, sticky="nsew")
        frame.columnconfigure(0, weight=1) # Cho phép trường nhập mở rộng

        ttk.Label(frame, text="Nhập Mật khẩu Master:", font=('Arial', 11)).grid(row=0, column=0, sticky="w")
        self.password_var = tk.StringVar()
        self.password_entry = ttk.Entry(frame, textvariable=self.password_var, show="*")
        self.password_entry.grid(row=1, column=0, sticky="ew", pady=(3, 5))
        ToolTip(self.password_entry, "Mật khẩu chính dùng để mã hóa/giải mã dữ liệu của bạn")

        self.show_password_var = tk.BooleanVar(value=False)
        self.show_password_check = ttk.Checkbutton(frame, text="Hiển thị mật khẩu", variable=self.show_password_var, command=self._toggle_password)
        self.show_password_check.grid(row=2, column=0, sticky="w")

        if self.first_time:
            ttk.Label(frame, text="Xác nhận Mật khẩu Master:", font=('Arial', 11)).grid(row=3, column=0, sticky="w", pady=(10, 0))
            self.confirm_var = tk.StringVar()
            self.confirm_entry = ttk.Entry(frame, textvariable=self.confirm_var, show="*")
            self.confirm_entry.grid(row=4, column=0, sticky="ew", pady=(3, 5))
            ToolTip(self.confirm_entry, "Nhập lại mật khẩu để xác nhận")

            self.show_confirm_var = tk.BooleanVar(value=False)
            self.show_confirm_check = ttk.Checkbutton(frame, text="Hiển thị mật khẩu", variable=self.show_confirm_var, command=self._toggle_confirm_password)
            self.show_confirm_check.grid(row=5, column=0, sticky="w")

        button_frame = ttk.Frame(frame)
        button_row = 6 if self.first_time else 3
        button_frame.grid(row=button_row, column=0, pady=(15, 0), sticky="e")
        self.ok_btn = ttk.Button(button_frame, text="ĐỒNG Ý", command=self.on_ok)
        self.ok_btn.grid(row=0, column=0, padx=5)
        self.cancel_btn = ttk.Button(button_frame, text="HỦY", command=self.on_cancel)
        self.cancel_btn.grid(row=0, column=1, padx=5)

        # Ràng buộc phím Enter và Escape
        self.bind("<Return>", lambda e:self.on_ok())
        self.bind("<Escape>", lambda e:self.on_cancel())

        self.password_entry.focus_set() # Đặt focus vào trường nhập mật khẩu ban đầu

    def _toggle_password(self):
        """Bật/tắt hiển thị mật khẩu."""
        self.password_entry.config(show="" if self.show_password_var.get() else "*")

    def _toggle_confirm_password(self):
        """Bật/tắt hiển thị mật khẩu xác nhận (chỉ khi thiết lập lần đầu)."""
        if self.first_time:
             self.confirm_entry.config(show="" if self.show_confirm_var.get() else "*")

    def on_ok(self):
        """Xử lý khi nhấn nút ĐỒNG Ý."""
        pwd = self.password_var.get().strip()
        if not pwd:
            messagebox.showwarning("Yêu cầu nhập liệu", "Mật khẩu Master không được để trống.", parent=self)
            return
        if self.first_time:
            confirm = self.confirm_var.get().strip()
            if pwd != confirm:
                messagebox.showerror("Không khớp", "Mật khẩu xác nhận không khớp.", parent=self)
                return
        self.result = pwd
        self.destroy() # Đóng hộp thoại

    def on_cancel(self):
        """Xử lý khi nhấn nút HỦY hoặc đóng hộp thoại."""
        self.result = None
        self.destroy() # Đóng hộp thoại

# --- Helper function to get master password ---
def get_master_password(root, first_time=False):
    """Hiển thị hộp thoại yêu cầu mật khẩu master."""
    # Kiểm tra xem cửa sổ root có tồn tại không trước khi tạo dialog
    if not root or not root.winfo_exists():
         print("Lỗi: Không thể hiển thị hộp thoại mật khẩu, cửa sổ root không tồn tại.")
         return None
    dialog = MasterPasswordDialog(root, first_time=first_time)
    root.wait_window(dialog) # Chờ cho đến khi hộp thoại bị đóng
    return dialog.result

# --- ToolTip Class ---
class ToolTip:
    """Hiển thị tooltip khi di chuột qua widget."""
    def __init__(self, widget, text):
        self.widget = widget
        self.text = text
        self.tipwindow = None
        self.id = None
        self.x = self.y = 0
        self.widget.bind("<Enter>", self.showtip)
        self.widget.bind("<Leave>", self.hidetip)
        self.widget.bind("<ButtonPress>", self.hidetip)

    def showtip(self, event):
        """Hiển thị tooltip."""
        if self.tipwindow or not self.text: return
        # Tính toán vị trí của cửa sổ tooltip so với widget
        x, y, _, _ = self.widget.bbox("insert") or (0,0,0,0) # Lấy tọa độ con trỏ hoặc (0,0,0,0)
        x = x + self.widget.winfo_rootx() + 20 # Vị trí X tuyệt đối trên màn hình
        y = y + self.widget.winfo_rooty() + self.widget.winfo_height() + 5 # Vị trí Y tuyệt đối trên màn hình

        # Tạo cửa sổ tooltip (không có khung viền)
        self.tipwindow = tw = tk.Toplevel(self.widget)
        tw.wm_overrideredirect(True)

        # Tạo nhãn chứa nội dung tooltip để tính kích thước
        label = tk.Label(tw, text=self.text, justify=tk.LEFT,
                         background="#ffffe0", relief=tk.SOLID, borderwidth=1,
                         font=("tahoma", "8", "normal"), padx=5, pady=4)
        label.pack(ipadx=1)

        # Cập nhật layout để lấy kích thước chính xác của cửa sổ tooltip
        tw.update_idletasks()
        tip_width = tw.winfo_width()
        tip_height = tw.winfo_height()

        # Điều chỉnh vị trí nếu tooltip bị tràn ra khỏi màn hình (kiểm tra cơ bản)
        screen_width = self.widget.winfo_screenwidth()
        screen_height = self.widget.winfo_screenheight()

        if x + tip_width > screen_width:
            x = screen_width - tip_width - 5 # Cách lề phải 5 pixel
        if y + tip_height > screen_height:
             # Thử đặt phía trên widget thay vì phía dưới
             y = self.widget.winfo_rooty() - tip_height - 5

        # Đặt hình học (vị trí) cho cửa sổ tooltip
        tw.wm_geometry(f"+{x}+{y}")


    def hidetip(self, event=None):
        """Ẩn tooltip."""
        tw = self.tipwindow
        self.tipwindow = None
        if tw: tw.destroy()

# -------- EncryptionManager ------------

class EncryptionManager:
    """Quản lý việc tạo khóa mã hóa và mã hóa/giải mã dữ liệu bằng Fernet."""
    def __init__(self):
        self._pdk = None # Password Derived Key
        self._fernet_key = None # Khóa Fernet thực tế để mã hóa dữ liệu
        self.fernet = None # Đối tượng Fernet cipher
        self._salt = self._load_or_create_salt() # Salt cho PBKDF2
        if self._salt is None:
            return # Khởi tạo thất bại

    def _load_or_create_salt(self):
        """Tải salt từ file hoặc tạo salt mới nếu file không tồn tại."""
        if os.path.exists(SALT_FILE):
            try:
                with open(SALT_FILE, "rb") as f:
                    salt = f.read()
                # Salt phải có độ dài 16 bytes
                if salt is None or len(salt) != 16:
                    print(f"File salt bị hỏng hoặc không hợp lệ: {SALT_FILE}")
                    raise ValueError("File salt bị hỏng hoặc không hợp lệ.")
                print(f"Đã tải salt từ {SALT_FILE}")
                return salt
            except Exception as e:
                # Xử lý hộp thoại messagebox có thể xuất hiện trước khi root được khởi tạo hoàn toàn
                try:
                     messagebox.showerror("Lỗi File", f"Không đọc hoặc xác thực được file salt: {str(e)}", parent=None)
                except Exception: print(f"Lỗi File: Không đọc hoặc xác thực được file salt: {str(e)}")
                return None
        else:
            salt = os.urandom(16) # Tạo salt ngẫu nhiên (16 bytes)
            try:
                with open(SALT_FILE, "wb") as f:
                    f.write(salt)
                print(f"Đã tạo và lưu salt mới vào {SALT_FILE}")
                return salt
            except Exception as e:
                try:
                    messagebox.showerror("Lỗi File", f"Không ghi được file salt: {str(e)}", parent=None)
                except Exception: print(f"Lỗi File: Không ghi được file salt: {str(e)}")
                return None

    def derive_pdk(self, password: str) -> bytes:
        """Tạo Khóa Dẫn Xuất Từ Mật khẩu (PDK) từ mật khẩu và salt đã lưu."""
        if self._salt is None:
            raise ValueError("Salt chưa được tải hoặc tạo.")
        kdf = PBKDF2HMAC(
            algorithm=hashes.SHA256(),
            length=32, # PDK có độ dài 32 bytes (256 bits)
            salt=self._salt,
            iterations=600000, # Số vòng lặp cao để chống brute-force
        )
        return kdf.derive(password.encode('utf-8'))

    def verify_and_load_key(self, password: str) -> bool:
        """
        Xác thực mật khẩu bằng cách giải mã khóa Fernet đã lưu.
        Tải và khởi tạo đối tượng Fernet chính khi thành công.
        """
        if self._salt is None:
             # Salt loading failed previously
             # message box already shown in _load_or_create_salt
             return False

        try:
            pdk = self.derive_pdk(password) # Tạo PDK từ mật khẩu người dùng
            if os.path.exists(ENCRYPTED_FERNET_KEY_FILE):
                # File khóa Fernet đã tồn tại, thử giải mã
                with open(ENCRYPTED_FERNET_KEY_FILE, "rb") as f:
                    encrypted_fern_key = f.read()

                # Sử dụng PDK làm khóa để giải mã khóa Fernet
                # PDK phải được base64 urlsafe encode để được sử dụng làm khóa cho Fernet (để mã hóa khóa khác)
                pdk_fernet_key_b64 = base64.urlsafe_b64encode(pdk)
                pdk_fernet = Fernet(pdk_fernet_key_b64) # Đối tượng Fernet dùng cho PDK

                try:
                    decrypted_fern_key = pdk_fernet.decrypt(encrypted_fern_key)
                    if len(decrypted_fern_key) != 32: # Kiểm tra độ dài khóa giải mã có đúng 32 bytes không
                        raise InvalidToken("Khóa giải mã có độ dài không hợp lệ.")

                    # Giải mã thành công! Lưu PDK, khóa Fernet và khởi tạo đối tượng Fernet chính
                    self._pdk = pdk
                    self._fernet_key = decrypted_fern_key
                    # Khóa Fernet thực tế (đã giải mã) cũng phải được base64 urlsafe encode để tạo đối tượng Fernet chính
                    self.fernet = Fernet(base64.urlsafe_b64encode(self._fernet_key))

                    print("Đã tải và xác thực khóa Fernet.")
                    return True

                except InvalidToken:
                    # Mật khẩu sai, giải mã thất bại
                    print("Giải mã khóa Fernet thất bại (mật khẩu sai).")
                    return False # Báo hiệu xác thực thất bại

                except Exception as e:
                    # Các lỗi giải mã khác
                    messagebox.showerror("Lỗi Giải mã", f"Không giải mã được file khóa: {str(e)}", parent=None)
                    return False

            else:
                # File khóa Fernet KHÔNG tồn tại - có lẽ là lần chạy đầu tiên sau khi thiết lập mật khẩu
                # Tạo khóa Fernet mới, mã hóa nó bằng PDK và lưu lại
                raw_fern_key = os.urandom(32) # Khóa thực tế để mã hóa dữ liệu người dùng (32 bytes)

                # Sử dụng PDK làm khóa để mã hóa khóa Fernet thực tế
                pdk_fernet_key_b64 = base64.urlsafe_b64encode(pdk)
                pdk_fernet = Fernet(pdk_fernet_key_b64) # Đối tượng Fernet dùng cho PDK

                encrypted_fern_key = pdk_fernet.encrypt(raw_fern_key) # Mã hóa khóa dữ liệu người dùng bằng PDK

                try:
                    with open(ENCRYPTED_FERNET_KEY_FILE, "wb") as f:
                        f.write(encrypted_fern_key)

                    # Thành công! Lưu khóa và khởi tạo đối tượng Fernet chính
                    self._pdk = pdk
                    self._fernet_key = raw_fern_key
                    # Khóa Fernet thực tế (raw_fern_key) phải được base64 urlsafe encode để tạo đối tượng Fernet chính
                    self.fernet = Fernet(base64.urlsafe_b64encode(self._fernet_key))
                    print("Đã tạo và lưu khóa Fernet mới.")
                    # Không hiển thị messagebox ở đây, hộp thoại MasterPasswordDialog đã xử lý thông báo "Thiết lập hoàn tất"
                    return True # Báo hiệu thành công

                except Exception as e:
                    messagebox.showerror("Lỗi File", f"Không lưu được file khóa mã hóa mới: {str(e)}", parent=None)
                    return False

        except Exception as e:
            # Lỗi trong quá trình tạo PDK hoặc các vấn đề không mong muốn khác
            messagebox.showerror("Lỗi Thiết lập Mã hóa", f"Đã xảy ra lỗi trong quá trình thiết lập khóa: {str(e)}", parent=None)
            return False

    def encrypt(self, data: str) -> str:
        """Mã hóa dữ liệu sử dụng khóa Fernet đã tải."""
        if not data: return ""
        if self.fernet is None:
             print("Cảnh báo: Mã hóa thất bại. Đối tượng Fernet cipher chưa được khởi tạo.")
             return "" # Không thể mã hóa nếu không có khóa
        try:
            # Dữ liệu cần là bytes để Fernet mã hóa, trả về chuỗi ascii base64
            return self.fernet.encrypt(data.encode('utf-8')).decode('ascii')
        except Exception as e:
             print(f"Mã hóa thất bại cho dữ liệu: {data[:50]}... Lỗi: {e}")
             return "" # Trả về chuỗi rỗng nếu mã hóa thất bại

    def decrypt(self, encrypted_data: str) -> str:
        """Giải mã dữ liệu sử dụng khóa Fernet đã tải."""
        if not encrypted_data: return ""
        if self.fernet is None:
            print("Cảnh báo: Giải mã thất bại. Đối tượng Fernet cipher chưa được khởi tạo.")
            return "" # Không thể giải mã nếu không có khóa
        try:
            # Dữ liệu mã hóa cần là bytes ascii cho Fernet, trả về chuỗi utf-8 đã giải mã
            return self.fernet.decrypt(encrypted_data.encode('ascii')).decode('utf-8')
        except InvalidToken:
             # Thường xảy ra với chuỗi rỗng, dữ liệu cũ chưa mã hóa hoặc dữ liệu bị hỏng.
             # Trả về chuỗi rỗng thường được chấp nhận trong trường hợp này.
             # print(f"Giải mã thất bại: Invalid token cho dữ liệu: {encrypted_data[:50]}...") # Ghi log tùy chọn
             return ""
        except Exception as e:
             print(f"Giải mã thất bại: Lỗi không mong muốn cho dữ liệu: {encrypted_data[:50]}... Lỗi: {e}")
             # Ghi log lỗi không mong muốn
             return ""

    # Hàm này cần PDK hiện tại và mật khẩu mới để tạo PDK mới và mã hóa lại khóa Fernet
    def re_encrypt_fernet_key_with_new_password(self, old_password: str, new_password: str) -> bool:
        """
        Xác thực mật khẩu cũ, tạo PDK mới từ mật khẩu mới,
        mã hóa lại khóa Fernet bằng PDK mới và lưu lại.
        """
        if self._salt is None:
             messagebox.showerror("Lỗi", "Không có salt để thực hiện đổi mật khẩu.", parent=None)
             return False

        try:
            # 1. Xác thực mật khẩu cũ bằng cách thử giải mã khóa Fernet
            pdk_old = self.derive_pdk(old_password)
            # Sử dụng PDK cũ làm khóa để giải mã khóa Fernet
            pdk_old_fernet_key_b64 = base64.urlsafe_b64encode(pdk_old)
            pdk_old_fernet = Fernet(pdk_old_fernet_key_b64)

            with open(ENCRYPTED_FERNET_KEY_FILE, "rb") as f:
                 encrypted_fern_key_old = f.read()

            try:
                 # Đây là khóa Fernet thực tế mà chúng ta cần bảo toàn
                 decrypted_fern_key = pdk_old_fernet.decrypt(encrypted_fern_key_old)
                 if len(decrypted_fern_key) != 32:
                      raise InvalidToken("Khóa giải mã có độ dài không hợp lệ khi xác thực mật khẩu cũ.")
                 print("Xác thực mật khẩu cũ thành công.")

            except InvalidToken:
                 print("Xác thực mật khẩu cũ thất bại (mật khẩu sai).")
                 return False # Mật khẩu cũ sai

            # 2. Tạo PDK mới từ mật khẩu mới
            pdk_new = self.derive_pdk(new_password)
            # Sử dụng PDK mới làm khóa để mã hóa lại khóa Fernet thực tế
            pdk_new_fernet_key_b64 = base64.urlsafe_b64encode(pdk_new)
            pdk_new_fernet = Fernet(pdk_new_fernet_key_b64)

            # 3. Mã hóa lại khóa Fernet thực tế bằng PDK mới
            encrypted_fern_key_new = pdk_new_fernet.encrypt(decrypted_fern_key)

            # 4. Lưu khóa Fernet đã mã hóa mới vào file (ghi đè)
            try:
                with open(ENCRYPTED_FERNET_KEY_FILE, "wb") as f:
                    f.write(encrypted_fern_key_new)

                # 5. Cập nhật trạng thái trong EncryptionManager với PDK mới và đối tượng Fernet mới
                self._pdk = pdk_new # Lưu PDK mới
                # self._fernet_key vẫn giữ nguyên giá trị (đã giải mã)
                # Cập nhật đối tượng Fernet chính để đảm bảo nó sử dụng khóa Fernet với PDK mới
                self.fernet = Fernet(base64.urlsafe_b64encode(self._fernet_key))

                print("Đã mã hóa lại và lưu khóa Fernet thành công với mật khẩu mới.")
                return True

            except Exception as e:
                 messagebox.showerror("Lỗi File", f"Không lưu được file khóa mã hóa lại: {str(e)}", parent=None)
                 return False

        except Exception as e:
            messagebox.showerror("Lỗi Đổi mật khẩu", f"Đã xảy ra lỗi trong quá trình đổi mật khẩu: {str(e)}", parent=None)
            return False

# -------- Change Password Dialog ---------
class ChangePasswordDialog(tk.Toplevel):
     """Hộp thoại để người dùng đổi mật khẩu master."""
     def __init__(self, parent, encryption_manager):
          super().__init__(parent)
          self.parent = parent
          self.encryption_manager = encryption_manager
          self.result = False # True nếu đổi mật khẩu thành công

          self.title("Đổi Mật khẩu Master")
          self.resizable(False, False)
          self.transient(parent)
          self.grab_set()
          self.protocol("WM_DELETE_WINDOW", self.on_cancel)

          self._build_ui()
          self._center_window() # Căn giữa hộp thoại so với cửa sổ cha

          self.attributes('-topmost', True)
          self.focus_force()
          self.after(50, lambda: self.attributes('-topmost', False))


     def _center_window(self):
          # (Copy logic từ MasterPasswordDialog._center_window)
          if not self.parent or not self.parent.winfo_exists():
              print("Cảnh báo: Không thể căn giữa hộp thoại, cửa sổ cha không tồn tại.")
              return
          self.update_idletasks()
          width = self.winfo_reqwidth()
          height = self.winfo_reqheight()
          parent_x = self.parent.winfo_x()
          parent_y = self.parent.winfo_y()
          parent_width = self.parent.winfo_width()
          parent_height = self.parent.winfo_height()
          x = parent_x + (parent_width // 2) - (width // 2)
          y = parent_y + (parent_height // 2) - (height // 2)
          self.geometry(f"{width}x{height}+{x}+{y}")
          self.minsize(width, height)


     def _build_ui(self):
          pad = 10
          frame = ttk.Frame(self, padding=pad)
          frame.grid(row=0, column=0, sticky="nsew")
          frame.columnconfigure(0, weight=1)

          # Mật khẩu cũ
          ttk.Label(frame, text="Mật khẩu cũ:", font=('Arial', 10)).grid(row=0, column=0, sticky="w")
          self.old_password_var = tk.StringVar()
          self.old_password_entry = ttk.Entry(frame, textvariable=self.old_password_var, show="*", width=40)
          self.old_password_entry.grid(row=1, column=0, sticky="ew", pady=(3, 5))
          ToolTip(self.old_password_entry, "Nhập mật khẩu master hiện tại của bạn")

          # Mật khẩu mới
          ttk.Label(frame, text="Mật khẩu mới:", font=('Arial', 10)).grid(row=2, column=0, sticky="w", pady=(10,0))
          self.new_password_var = tk.StringVar()
          self.new_password_entry = ttk.Entry(frame, textvariable=self.new_password_var, show="*", width=40)
          self.new_password_entry.grid(row=3, column=0, sticky="ew", pady=(3, 5))
          ToolTip(self.new_password_entry, "Nhập mật khẩu master mới")

          # Xác nhận mật khẩu mới
          ttk.Label(frame, text="Xác nhận mật khẩu mới:", font=('Arial', 10)).grid(row=4, column=0, sticky="w", pady=(10,0))
          self.confirm_new_password_var = tk.StringVar()
          self.confirm_new_password_entry = ttk.Entry(frame, textvariable=self.confirm_new_password_var, show="*", width=40)
          self.confirm_new_password_entry.grid(row=5, column=0, sticky="ew", pady=(3, 5))
          ToolTip(self.confirm_new_password_entry, "Nhập lại mật khẩu mới để xác nhận")

          # Checkbox hiển thị mật khẩu (có thể thêm cho cả 3 trường)
          self.show_passwords_var = tk.BooleanVar(value=False)
          self.show_passwords_check = ttk.Checkbutton(frame, text="Hiển thị mật khẩu", variable=self.show_passwords_var, command=self._toggle_password_visibility)
          self.show_passwords_check.grid(row=6, column=0, sticky="w", pady=(5, 0))


          button_frame = ttk.Frame(frame)
          button_frame.grid(row=7, column=0, pady=(15, 0), sticky="e")
          ttk.Button(button_frame, text="ĐỔI MẬT KHẨU", command=self.on_change_password).grid(row=0, column=0, padx=5)
          ttk.Button(button_frame, text="HỦY", command=self.on_cancel).grid(row=0, column=1, padx=5)

          self.old_password_entry.focus_set()

     def _toggle_password_visibility(self):
          """Bật/tắt hiển thị mật khẩu cho cả 3 trường."""
          show = "" if self.show_passwords_var.get() else "*"
          self.old_password_entry.config(show=show)
          self.new_password_entry.config(show=show)
          self.confirm_new_password_entry.config(show=show)

     def on_change_password(self):
          """Xử lý khi nhấn nút ĐỔI MẬT KHẨU."""
          old_pwd = self.old_password_var.get().strip()
          new_pwd = self.new_password_var.get().strip()
          confirm_new_pwd = self.confirm_new_password_var.get().strip()

          # Xác thực nhập liệu cơ bản
          if not old_pwd or not new_pwd or not confirm_new_pwd:
               messagebox.showwarning("Thiếu thông tin", "Vui lòng điền đầy đủ cả ba trường.", parent=self)
               return

          if new_pwd != confirm_new_pwd:
               messagebox.showerror("Không khớp", "Mật khẩu mới và xác nhận mật khẩu mới không khớp.", parent=self)
               self.new_password_entry.focus_set()
               return

          # Thực hiện đổi mật khẩu trong EncryptionManager
          if self.encryption_manager.re_encrypt_fernet_key_with_new_password(old_pwd, new_pwd):
               self.result = True
               messagebox.showinfo("Thành công", "Mật khẩu Master đã được đổi thành công.", parent=self)
               self.destroy()
          else:
               # re_encrypt_fernet_key_with_new_password sẽ trả về False nếu mật khẩu cũ sai
               # hoặc có lỗi trong quá trình lưu file. Thông báo lỗi đã được hiển thị bên trong.
               # Chỉ cần đặt focus lại vào trường mật khẩu cũ nếu xác thực mật khẩu cũ sai.
               self.old_password_entry.focus_set()
               # Không đóng cửa sổ nếu đổi mật khẩu thất bại


     def on_cancel(self):
          """Xử lý khi nhấn nút HỦY hoặc đóng hộp thoại."""
          self.result = False
          self.destroy()

# ------------ YouTube Channel Manager Main Class ------------
class YouTubeChannelManager:
    def __init__(self, root, encryption_manager_instance):
        self.root = root
        self.encryption_manager = encryption_manager_instance

        # --- Cấu hình cửa sổ chính ban đầu (trước xác thực) ---
        # Chỉ đặt tiêu đề, kích thước và minsize ban đầu. CHƯA căn giữa ngay.
        self.root.title("Quản lý Kênh YouTube")
        self.root.geometry("1100x750") # Đặt kích thước ban đầu
        self.root.minsize(900, 600)

        # Cờ theo dõi trạng thái khóa ứng dụng
        self._is_locked = False

        # Biến theo dõi thời gian không hoạt động cho chức năng tự động khóa
        self._last_activity_time = time.time()
        self._auto_lock_job = None # Biến để lưu trữ id của scheduled job


        # --- Cấu hình Styles ---
        self.style = ttk.Style()
        self.style.theme_use('clam') # Một theme sạch sẽ, hiện đại
        # Cấu hình kích thước font mặc định
        default_font = tkfont.nametofont("TkDefaultFont")
        default_font.configure(size=10)
        # Định nghĩa các font tùy chỉnh để nhất quán
        self.title_font = ('Arial', 12, 'bold')
        self.button_font = ('Arial', 10)
        self.label_font = ('Arial', 10)
        self.entry_font = ('Arial', 10)
        self.text_font = ('Arial', 10) # Font cho Text widget

        # Cấu hình style cho các widget cụ thể
        self.style.configure('TNotebook.Tab', padding=[10, 5], font=self.button_font)
        self.style.configure('Treeview', font=('Arial', 9), rowheight=22) # Điều chỉnh chiều cao hàng để dễ đọc
        self.style.configure('Treeview.Heading', font=('Arial', 9, 'bold'))
        # Style tùy chỉnh cho các nút chính
        self.style.configure('Accent.TButton', background='#3498db', foreground='white', font=self.button_font)
        self.style.map('Accent.TButton', background=[('active', '#2980b9')]) # Xanh đậm hơn khi di chuột qua
        # Style cho trường nhập liệu khi có lỗi xác thực
        self.style.configure('Error.TEntry', fieldbackground='#f0c0c0') # Nền đỏ nhạt
        self.style.map('TEntry', fieldbackground=[('!focus', 'white'), ('focus', '#e8f0fe')]) # Nền trắng mặc định, xanh nhạt khi focus
        self.style.map('Error.TEntry', fieldbackground=[('!focus', '#f0c0c0'), ('focus', '#f0c0c0')]) # Nền đỏ nhạt bất kể focus

        # --- Xác thực Mật khẩu Master ---
        self.master_password_verified = False
        first_run = not os.path.exists(ENCRYPTED_FERNET_KEY_FILE)

        if first_run:
            # Thiết lập ban đầu: Yêu cầu mật khẩu và thiết lập
            while True:
                # Hộp thoại mật khẩu sẽ được căn giữa so với cửa sổ root
                master_pwd = get_master_password(self.root, first_time=True)
                if master_pwd is None:
                    messagebox.showerror("Thiết lập Đã hủy", "Thiết lập mật khẩu master đã bị hủy. Ứng dụng sẽ thoát.", parent=self.root)
                    self.root.destroy()
                    return # Thoát nếu thiết lập bị hủy
                # verify_and_load_key xử lý việc tạo và lưu khóa fernet ở chế độ first_run
                if self.encryption_manager.verify_and_load_key(master_pwd):
                    self.master_password_verified = True
                    # verify_and_load_key đã hiển thị thông báo thành công ở chế độ first_run
                    break # Thoát vòng lặp khi thành công
                else:
                    # verify_and_load_key hiển thị thông báo lỗi cụ thể (ví dụ: lỗi file)
                    # Vòng lặp tiếp tục cho lần thử khác hoặc hủy bỏ
                    # MessageBox đã hiển thị, không cần thêm ở đây
                    pass # Do nothing more, the loop continues

        else:
            # Thiết lập đã tồn tại: Yêu cầu mật khẩu và xác thực
            password_verified = False
            attempts = 3 # Số lần thử tối đa
            while attempts > 0:
                # Hộp thoại mật khẩu sẽ được căn giữa so với cửa sổ root
                master_pwd = get_master_password(self.root)
                if master_pwd is None:
                    messagebox.showerror("Xác thực Đã hủy", "Xác thực mật khẩu master đã bị hủy. Ứng dụng sẽ thoát.", parent=self.root)
                    self.root.destroy()
                    return # Thoát nếu bị hủy

                if self.encryption_manager.verify_and_load_key(master_pwd):
                    password_verified = True
                    break # Xác thực thành công

                else:
                    attempts -= 1
                    if attempts > 0:
                        messagebox.showerror("Mật khẩu Sai", f"Mật khẩu master không đúng! Số lần thử còn lại: {attempts}", parent=self.root)
                    else:
                        messagebox.showerror("Xác thực Thất bại", "Số lần thử không đúng quá nhiều. Ứng dụng sẽ thoát.", parent=self.root)
                        self.root.destroy()
                        return # Thoát sau khi hết số lần thử không đúng

            if not password_verified:
                # Trường hợp này về mặt lý thuyết không xảy ra nếu attempts đạt 0 và chúng ta thoát,
                # nhưng được bao gồm để đảm bảo độ bền.
                self.root.destroy()
                return

            self.master_password_verified = True
            # print("Xác thực thành công.") # Đã được in bởi verify_and_load_key, nhưng vô hại

        # --- Khởi tạo Trạng thái Ứng dụng nếu xác thực thành công ---
        # Chỉ tiếp tục nếu master_password_verified là True VÀ cửa sổ root vẫn tồn tại (chưa bị root.destroy())
        if not self.master_password_verified or not self.root.winfo_exists():
            # Điều này xảy ra nếu root.destroy() được gọi trong quá trình xác thực
            return

        print("Đang khởi tạo giao diện ứng dụng...")

        # --- BÂY GIỜ, căn giữa cửa sổ chính và xây dựng phần còn lại của giao diện ---
        self.center_main_window() # GỌI CENTER SAU KHI XÁC THỰC HOÀN TẤT

        # Set App ID (Windows)
        if os.name == 'nt':
            myappid = "YouTubeChannelManager.App.2.7" # Tăng version nếu có thay đổi đáng kể
            try: ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID(myappid)
            except Exception as e: print(f"Cảnh báo: Không thể đặt AppUserModelID - {e}")

        # Đặt Icon
        try:
            icon_path = 'Logo.ico' # Ưu tiên .ico cho tương thích tốt hơn trên Windows
            if os.path.exists(icon_path): self.root.iconbitmap(icon_path)
            else:
                 # Dự phòng sang .png
                 png_icon_path = 'Logo.png'
                 if os.path.exists(png_icon_path):
                     try:
                         # Sử dụng PhotoImage cho icon .png trên Tkinter
                         photo = tk.PhotoImage(file=png_icon_path)
                         self.root._icon_photo = photo # Giữ tham chiếu để ngăn garbage collection
                         self.root.tk.call('wm', 'iconphoto', self.root._w, self.root._icon_photo)
                     except Exception as e: print(f"Cảnh báo: Không thể đặt icon .png - {e}")
                 else: print("Cảnh báo: Không tìm thấy file icon (Logo.ico hoặc Logo.png).")
        except Exception as e: print(f"Cảnh báo: Không thể tải icon - {e}")


        # --- Tải Dữ liệu (sau khi khóa mã hóa đã được xác thực/tải) ---
        self.data = self._load_data()
        self._data_changed = False # Cờ để theo dõi các thay đổi chưa lưu

        # --- Khởi tạo Biến Giao diện Người dùng ---
        self.selected_email_index = None # Chỉ mục của email đang được chọn trong self.data
        self.selected_channel_index = None # Chỉ mục của kênh đang được chọn trong danh sách kênh của email đã chọn
        self.otp_thread_id = None # Mã định danh cho luồng OTP hiện tại để quản lý vòng đời của nó
        self.show_password = tk.BooleanVar(value=False) # Biến cho chức năng bật/tắt hiển thị mật khẩu

        # Biến chi tiết Email được kết nối với các widget giao diện
        self.is_verified_var = tk.BooleanVar(value=False)
        self.verified_by_var = tk.StringVar(value="")
        self.login_location_var = tk.StringVar(value="")
        self.verification_failed_var = tk.BooleanVar(value=False)

        # Biến QR code và tham chiếu ảnh
        self.qrcode_image_base64_decrypted_var = tk.StringVar(value="") # Lưu chuỗi base64 (đã giải mã)
        self.qrcode_photo_image = None # Tham chiếu đến đối tượng Tkinter PhotoImage

        # Biến liên quan đến tìm kiếm và trace IDs
        self.global_search_var = tk.StringVar()
        # Ràng buộc hàm tìm kiếm với sự thay đổi trong biến nhập liệu tìm kiếm
        self._search_trace_id = self.global_search_var.trace_add("write", self.perform_global_search)
        self.search_scope = tk.StringVar(value="all") # Biến cho các nút radio phạm vi tìm kiếm
        self.filter_in_use = tk.BooleanVar(value=False) # Biến cho checkbox lọc 'chỉ đang sử dụng'
        # Ràng buộc hàm tìm kiếm với sự thay đổi trong biến checkbox lọc
        self._filter_trace_id = self.filter_in_use.trace_add("write", self.perform_global_search)
        self.search_results = [] # Lưu cấu trúc dữ liệu đã lọc cho chế độ tìm kiếm
        self.current_view = "normal" # Theo dõi chế độ xem hiện tại ('normal' data hoặc 'search' results)

        # Biến liên quan đến sắp xếp
        self.current_channels = [] # Danh sách các kênh đang được hiển thị trong treeview kênh
        self._email_sort_col = None # Cột hiện tại đang được sắp xếp trong treeview email
        self._email_sort_order = False # Thứ tự sắp xếp (False cho tăng dần, True cho giảm dần)
        self._channel_sort_col = None # Cột hiện tại đang được sắp xếp trong treeview kênh
        self._channel_sort_order = False # Thứ tự sắp xếp (False cho tăng dần, True cho giảm dần)


        # --- Xây dựng Giao diện Người dùng ---
        self.build_ui() # Tạo các widget và cấu hình style
        self.refresh_email_list() # Hiển thị danh sách email ban đầu

        # --- Ràng buộc Sự kiện Toàn cục ---
        self.root.bind('<Control-n>', lambda e: self.add_email()) # Ctrl+N để thêm email mới
        self.root.bind('<Control-s>', lambda e: self.save_current_tab()) # Ctrl+S để lưu dữ liệu tab hiện tại
        self.root.bind('<Control-f>', lambda e: self.global_search_entry.focus_set()) # Ctrl+F để đặt focus vào ô tìm kiếm
        self.root.protocol("WM_DELETE_WINDOW", self.on_closing) # Xử lý sự kiện đóng cửa sổ

        # Ràng buộc sự kiện chuột và bàn phím để theo dõi hoạt động cho Auto-Lock
        self.root.bind('<Motion>', self._record_activity)
        self.root.bind('<Key>', self._record_activity)
        self.root.bind('<Button>', self._record_activity)

        # Khởi động trình kiểm tra tự động khóa nếu được cấu hình
        if AUTO_LOCK_TIMEOUT_MS is not None and AUTO_LOCK_TIMEOUT_MS > 0:
             self._schedule_auto_lock_check()


    def center_main_window(self):
        """Căn giữa cửa sổ chính của ứng dụng trên màn hình."""
        window = self.root
        # Kiểm tra xem cửa sổ có tồn tại không trước khi căn giữa
        if not window or not window.winfo_exists():
             return

        window.update_idletasks() # Đảm bảo cửa sổ được đo và kích thước được tính toán

        # Lấy kích thước hiện tại của cửa sổ (sau khi geometry("..."))
        width = window.winfo_width()
        height = window.winfo_height()

        # Lấy kích thước màn hình
        screen_width = window.winfo_screenwidth()
        screen_height = window.winfo_screenheight()

        # Tính toán vị trí để căn giữa
        x = (screen_width // 2) - (width // 2)
        y = (screen_height // 2) - (height // 2)

        # Đặt vị trí cho cửa sổ
        window.geometry(f'+{x}+{y}')

    # --- Auto-Lock Methods ---
    def _record_activity(self, event=None):
        """Ghi lại thời gian hoạt động gần nhất của người dùng."""
        # Chỉ cập nhật thời gian nếu ứng dụng không bị khóa
        if not self._is_locked:
             self._last_activity_time = time.time()
             # print("Activity recorded") # Ghi log cho debug

    def _schedule_auto_lock_check(self):
        """Lên lịch kiểm tra tự động khóa."""
        # Hủy lịch trình trước đó nếu có
        if self._auto_lock_job:
             self.root.after_cancel(self._auto_lock_job)

        # Lên lịch gọi _check_auto_lock sau 1 giây
        # (Kiểm tra thường xuyên hơn timeout để phát hiện sớm hơn)
        if self.root and self.root.winfo_exists():
             self._auto_lock_job = self.root.after(1000, self._check_auto_lock)


    def _check_auto_lock(self):
        """Kiểm tra xem có cần khóa ứng dụng không dựa trên thời gian không hoạt động."""
        # Chỉ kiểm tra nếu auto-lock được bật và ứng dụng chưa bị khóa
        if AUTO_LOCK_TIMEOUT_MS is not None and AUTO_LOCK_TIMEOUT_MS > 0 and not self._is_locked:
            idle_duration_ms = (time.time() - self._last_activity_time) * 1000 # Thời gian không hoạt động tính bằng mili giây
            # print(f"Idle for {idle_duration_ms:.0f} ms") # Ghi log cho debug

            if idle_duration_ms >= AUTO_LOCK_TIMEOUT_MS:
                 self.lock_application() # Khóa ứng dụng

        # Lên lịch kiểm tra tiếp theo
        self._schedule_auto_lock_check() # Luôn lên lịch kiểm tra tiếp theo


    def lock_application(self):
        """Khóa ứng dụng, ẩn giao diện và yêu cầu mật khẩu master để mở khóa."""
        if self._is_locked: return # Tránh khóa lại nếu đã bị khóa

        self._is_locked = True
        self.status_var.set("Ứng dụng đã bị khóa")
        print("Ứng dụng đã bị khóa do không hoạt động.")

        # Dừng luồng OTP nếu đang chạy
        self.otp_thread_id = None
        self.otp_label.config(text="------", foreground="gray")
        # self.otp_time_label.config(text="Đã khóa") # Loại bỏ self.otp_time_label
        # Cập nhật text item trên canvas
        if hasattr(self, 'otp_timer_text_item'):
             self.otp_canvas.itemconfig(self.otp_timer_text_item, text="")
        if hasattr(self, 'otp_arc'):
            self.otp_canvas.itemconfig(self.otp_arc, extent=0, outline='#bdc3c7')


        # Ẩn cửa sổ chính hoặc chỉ vô hiệu hóa tất cả các widget
        # Ẩn cửa sổ là phương pháp mạnh mẽ hơn
        self.root.withdraw() # Ẩn cửa sổ chính

        # Hiển thị hộp thoại mật khẩu để mở khóa
        # Hộp thoại này là modal và sẽ chặn cho đến khi được xử lý
        unlocked = False
        while not unlocked:
            # Sử dụng hộp thoại mật khẩu hiện có
            # Pass parent=None because the root window is hidden
            # If the root window is destroyed during password prompt, get_master_password returns None
            master_pwd = get_master_password(None)

            if master_pwd is None:
                # If user cancels the unlock dialog, quit the application
                print("Unlock cancelled. Quitting.")
                self.root.quit() # Use quit() instead of destroy() when window is hidden
                return

            # Try to re-authenticate with the master password
            # verify_and_load_key will reload the Fernet key if password is correct
            if self.encryption_manager.verify_and_load_key(master_pwd):
                unlocked = True
                print("Ứng dụng đã được mở khóa.")
                self.status_var.set("Đã mở khóa")
            else:
                 # verify_and_load_key already showed the "Wrong password" error
                 pass # The loop continues asking for password


        # If unlock is successful, show the main window again
        self.root.deiconify() # Show the main window again
        self._is_locked = False # Reset the lock flag

        # Refresh UI to ensure data is displayed correctly (even though data didn't change)
        self.refresh_email_list()
        self.clear_email_details()
        self.clear_channel_details()
        self.channel_tree.delete(*self.channel_tree.get_children())
        self.update_channel_quick_view([])

        # Reset last activity time and restart auto-lock check
        self._record_activity()
        self._schedule_auto_lock_check() # Ensure checks continue after unlock


    # --- Data Handling Methods ---
    def _load_data(self):
        """Tải dữ liệu từ file JSON và giải mã các trường nhạy cảm."""
        if not os.path.exists(FILE):
            print(f"Không tìm thấy file dữ liệu: {FILE}")
            return [] # Trả về danh sách rỗng nếu file không tồn tại

        # Đảm bảo đối tượng mã hóa đã được khởi tạo trước khi cố gắng giải mã
        if self.encryption_manager.fernet is None:
             # Điều này đáng lẽ đã được bắt trong quá trình xác thực, nhưng kiểm tra để đảm bảo
             # MessageBox đã hiển thị ở phần xác thực
             return [] # Trả về danh sách rỗng nếu không thể giải mã

        try:
            with open(FILE, "r", encoding="utf-8") as f:
                data = json.load(f)

            # Giải mã các trường nhạy cảm cho mỗi mục dữ liệu
            for item in data:
                # Sử dụng .get() với giá trị mặc định để truy cập khóa an toàn và xử lý các khóa bị thiếu
                item["email"] = item.get("email", "")
                # Giải mã các trường, xử lý InvalidToken tiềm ẩn (ví dụ: nếu dữ liệu chưa được mã hóa hoặc bị hỏng)
                item["password"] = self.encryption_manager.decrypt(item.get("password", ""))
                item["2fa_key"] = self.encryption_manager.decrypt(item.get("2fa_key", ""))
                item["recovery_email"] = self.encryption_manager.decrypt(item.get("recovery_email", ""))

                # === THÊM GIẢI MÃ CHO TRƯỜNG MẬT KHẨU KHÔI PHỤC ===
                item["recovery_password"] = self.encryption_manager.decrypt(item.get("recovery_password", ""))

                # Tải các trường không mã hóa, cung cấp giá trị mặc định
                item["email_note"] = item.get("email_note", "") # Tải trường Ghi chú Email
                item["recovery_phone"] = item.get("recovery_phone", "") # Tải trường Số điện thoại khôi phục mới

                item["is_verified"] = item.get("is_verified", False)
                item["verified_by"] = item.get("verified_by", "")
                item["login_location"] = item.get("login_location", "")
                # Tải trường mới cho trạng thái xác minh thất bại
                item["verification_failed"] = item.get("verification_failed", False)
                # Tải và giải mã ảnh mã QR (lưu dưới dạng chuỗi base64)
                encrypted_b64_img = item.get("qrcode_image_base64", "")
                item["qrcode_image_base64"] = self.encryption_manager.decrypt(encrypted_b64_img)
                # Đảm bảo danh sách kênh tồn tại
                channels_data = item.get("channels", [])
                item["channels"] = channels_data if channels_data is not None else [] # Đảm bảo luôn là list

            print(f"Đã tải dữ liệu thành công từ {FILE}.")
            return data

        except json.JSONDecodeError:
             messagebox.showerror("Lỗi File", f"Không giải mã được JSON từ {FILE}. File có thể bị hỏng.", parent=self.root)
             print(f"Lỗi giải mã JSON từ {FILE}")
             return [] # Trả về danh sách rỗng khi có lỗi JSON

        except Exception as e:
            # Bắt bất kỳ lỗi không mong muốn nào khác trong quá trình tải/giải mã
            messagebox.showerror("Lỗi Tải dữ liệu", f"Đã xảy ra lỗi không mong muốn trong khi tải dữ liệu: {str(e)}", parent=self.root)
            print(f"Lỗi không mong muốn trong khi tải dữ liệu: {e}")
            return [] # Trả về danh sách rỗng khi có lỗi không mong muốn

    def _save_data(self):
        """Mã hóa các trường nhạy cảm và lưu dữ liệu vào file JSON."""
        # Đảm bảo đối tượng mã hóa đã được khởi tạo trước khi cố gắng mã hóa và lưu
        if self.encryption_manager.fernet is None:
             messagebox.showerror("Lỗi Lưu dữ liệu", "Không thể lưu dữ liệu. Đối tượng mã hóa chưa được khởi tạo.", parent=self.root)
             print("Lỗi Lưu dữ liệu: Đối tượng Fernet cipher chưa được khởi tạo.")
             return

        try:
            data_to_save = []
            for item in self.data:
                # Tạo một bản sao để tránh sửa đổi danh sách dữ liệu trực tiếp trước khi lưu hoàn tất
                item_copy = item.copy()

                # Mã hóa các trường nhạy cảm
                item_copy["password"] = self.encryption_manager.encrypt(item.get("password", ""))
                item_copy["2fa_key"] = self.encryption_manager.encrypt(item.get("2fa_key", ""))
                item_copy["recovery_email"] = self.encryption_manager.encrypt(item.get("recovery_email", ""))
                # === THÊM MÃ HÓA CHO TRƯỜNG MẬT KHẨU KHÔI PHỤC ===
                item_copy["recovery_password"] = self.encryption_manager.encrypt(item.get("recovery_password", ""))

                item_copy["qrcode_image_base64"] = self.encryption_manager.encrypt(item.get("qrcode_image_base64", ""))

                # Bao gồm các trường không mã hóa trực tiếp
                item_copy["email"] = item.get("email", "")
                item_copy["email_note"] = item.get("email_note", "") # Lưu trường Ghi chú Email
                item_copy["recovery_phone"] = item.get("recovery_phone", "") # Lưu trường Số điện thoại khôi phục mới

                item_copy["is_verified"] = item.get("is_verified", False)
                item_copy["verified_by"] = item.get("verified_by", "")
                item_copy["login_location"] = item.get("login_location", "")
                item_copy["verification_failed"] = item.get("verification_failed", False) # Bao gồm trường mới

                # Bao gồm danh sách kênh trực tiếp (nội dung kênh không được mã hóa ở lớp này)
                channels_data = item.get("channels", [])
                item_copy["channels"] = channels_data if channels_data is not None else [] # Ensure saving a list

                data_to_save.append(item_copy)

            # Tạo bản sao lưu trước khi ghi dữ liệu mới
            self._create_backup()

            # Ghi dữ liệu đã mã hóa vào file
            with open(FILE, "w", encoding="utf-8") as f:
                # Sử dụng indent để dễ đọc (tùy chọn nhưng là thói quen tốt)
                json.dump(data_to_save, f, indent=2, ensure_ascii=False)

            self._data_changed = False # Đặt lại cờ dữ liệu đã thay đổi
            self.status_var.set("Đã lưu dữ liệu thành công.")
            print(f"Đã lưu dữ liệu thành công vào {FILE}.")

        except Exception as e:
            # Bắt bất kỳ lỗi nào trong quá trình mã hóa hoặc ghi file
            messagebox.showerror("Lỗi Lưu dữ liệu", f"Không lưu được file dữ liệu: {str(e)}", parent=self.root)
            self.status_var.set("Lỗi khi lưu dữ liệu!")
            print(f"Lỗi khi lưu dữ liệu: {e}")


    def _create_backup(self):
        """Tạo bản sao lưu bằng cách sao chép file dữ liệu hiện tại."""
        # Chỉ tạo bản sao lưu nếu file chính tồn tại
        if not os.path.exists(FILE):
            print("Thông tin sao lưu: File dữ liệu chính chưa tồn tại. Bỏ qua sao lưu.")
            return False

        try:
            # Tạo thư mục sao lưu nếu nó không tồn tại
            if not os.path.exists(BACKUP_DIR):
                os.makedirs(BACKUP_DIR)

            # Tạo timestamp cho tên file sao lưu
            timestamp = time.strftime("%Y%m%d_%H%M%S")
            backup_file_path = os.path.join(BACKUP_DIR, f"channels_backup_{timestamp}.json")

            # Sao chép file dữ liệu hiện tại đến vị trí sao lưu
            shutil.copy2(FILE, backup_file_path) # copy2 cố gắng giữ lại metadata

            print(f"Đã tạo bản sao lưu: {backup_file_path}")

            # Dọn dẹp các bản sao lưu cũ (chỉ giữ lại 10 bản mới nhất)
            backup_files = sorted(
                [f for f in os.listdir(BACKUP_DIR) if f.startswith('channels_backup_') and f.endswith('.json')],
                key=lambda f: os.path.getmtime(os.path.join(BACKUP_DIR, f)), # Sắp xếp theo thời gian sửa đổi
                reverse=True # Mới nhất lên đầu
            )

            for old_backup in backup_files[10:]: # Lặp qua các file vượt quá 10 bản mới nhất
                try:
                    os.remove(os.path.join(BACKUP_DIR, old_backup))
                    print(f"Đã xóa bản sao lưu cũ: {old_backup}")
                except OSError as e:
                     print(f"Lỗi khi dọn dẹp bản sao lưu {old_backup}: {e}")

            return True

        except Exception as e:
            # Bắt bất kỳ lỗi nào trong quá trình sao lưu
            print(f"Lỗi Sao lưu: Không tạo được bản sao lưu - {str(e)}")
            return False

    # --- Xây dựng Giao diện Người dùng ---
    def build_ui(self):
        """Xây dựng giao diện người dùng chính."""
        # Menu bar (để thêm chức năng Đổi mật khẩu sau này)
        menubar = tk.Menu(self.root)
        self.root.config(menu=menubar)

        filemenu = tk.Menu(menubar, tearoff=0)
        menubar.add_cascade(label="Tệp", menu=filemenu)
        filemenu.add_command(label="Lưu", command=self._save_data, accelerator="Ctrl+S")
        filemenu.add_command(label="Nhập từ Excel...", command=self.import_from_excel)
        filemenu.add_command(label="Xuất ra Excel...", command=self.export_to_excel)
        filemenu.add_separator()
        filemenu.add_command(label="Đổi Mật khẩu Master...", command=self.change_master_password) # Thêm mục đổi mật khẩu
        filemenu.add_separator()
        filemenu.add_command(label="Thoát", command=self.on_closing)


        # Bố cục chính: Một frame lấp đầy cửa sổ root, được chia thành 3 cột
        main_frame = ttk.Frame(self.root, padding="10")
        main_frame.pack(fill=tk.BOTH, expand=True)
        main_frame.grid_rowconfigure(0, weight=1) # Hàng 0 mở rộng theo chiều dọc
        main_frame.grid_columnconfigure(0, weight=1) # Cột 0 (trái) mở rộng
        main_frame.grid_columnconfigure(1, weight=3) # Cột 1 (giữa) mở rộng nhiều hơn
        main_frame.grid_columnconfigure(2, weight=2) # Cột 2 (phải) mở rộng

        # Bảng điều khiển bên trái (Danh sách Email & Nhập/Xuất)
        left_panel = ttk.LabelFrame(main_frame, text="Tài khoản Email", padding="10")
        left_panel.grid(row=0, column=0, sticky="nsew", padx=(0, 10))
        left_panel.grid_rowconfigure(0, weight=1) # Hàng 0 (treeview) mở rộng theo chiều dọc
        left_panel.grid_columnconfigure(0, weight=1) # Cột 0 (nội dung danh sách email) mở rộng

        # Frame cho Treeview Email và thanh cuộn của nó
        email_frame = ttk.Frame(left_panel)
        email_frame.grid(row=0, column=0, sticky="nsew")
        email_frame.grid_rowconfigure(0, weight=1)
        email_frame.grid_columnconfigure(0, weight=1)

        # Treeview Email: Hiển thị địa chỉ email và số lượng kênh
        self.email_tree = ttk.Treeview(email_frame, columns=('email', 'channel_count'), show='headings', height=25)
        # Định nghĩa tiêu đề và liên kết chúng với các phương thức sắp xếp
        self.email_tree.heading('email', text='Email', anchor=tk.W, command=lambda: self._sort_email_tree('email'))
        self.email_tree.heading('channel_count', text='Kênh', anchor=tk.CENTER, command=lambda: self._sort_email_tree('channel_count'))
        # Định nghĩa thuộc tính cột (chiều rộng, giãn nở, căn chỉnh)
        self.email_tree.column('email', width=250, stretch=tk.YES)
        self.email_tree.column('channel_count', width=80, stretch=tk.NO, anchor=tk.CENTER)
        # Cấu hình tag hàng để tạo kiểu trực quan (ví dụ: đã xác minh, đang sử dụng, xác minh thất bại)
        self.email_tree.tag_configure('in_use_tag', foreground='green')
        self.email_tree.tag_configure('verified_tag', foreground='blue', font=('Arial', 9, 'bold'))
        self.email_tree.tag_configure('verification_failed_tag', foreground='red', font=('Arial', 9, 'bold'))
        # Đặt Treeview và ràng buộc sự kiện chọn
        self.email_tree.grid(row=0, column=0, sticky="nsew")
        self.email_tree.bind("<<TreeviewSelect>>", self.on_email_select)

        # Thanh cuộn cho Treeview Email
        email_scrollbar = ttk.Scrollbar(email_frame, orient=tk.VERTICAL, command=self.email_tree.yview)
        email_scrollbar.grid(row=0, column=1, sticky="ns")
        self.email_tree.configure(yscrollcommand=email_scrollbar.set)

        # Frame cho các nút Thêm/Xóa Email
        email_button_frame = ttk.Frame(left_panel)
        email_button_frame.grid(row=1, column=0, sticky=tk.EW, pady=(10, 0))
        email_button_frame.columnconfigure(0, weight=1) # Căn giữa các nút bằng cách đặt trọng số bằng nhau
        email_button_frame.columnconfigure(1, weight=1)
        self.add_email_button = ttk.Button(email_button_frame, text="➕ Thêm Email", command=self.add_email, style='Accent.TButton')
        self.add_email_button.grid(row=0, column=0, sticky=tk.E, padx=2) # Dính vào phía Đông trong cột của nó
        ToolTip(self.add_email_button, "Thêm tài khoản email mới (Ctrl+N)")
        self.delete_email_button = ttk.Button(email_button_frame, text="🗑 Xóa Email", command=self.delete_email)
        self.delete_email_button.grid(row=0, column=1, sticky=tk.W, padx=2) # Dính vào phía Tây trong cột của nó
        ToolTip(self.delete_email_button, "Xóa tài khoản email đang chọn")

        # Frame cho các nút Nhập/Xuất Excel
        import_export_frame = ttk.Frame(left_panel) # Đặt dưới email_button_frame trong left_panel
        import_export_frame.grid(row=2, column=0, sticky=tk.EW, pady=(5, 0))
        import_export_frame.columnconfigure(0, weight=1) # Cho phép các nút mở rộng
        import_export_frame.columnconfigure(1, weight=1)

        self.import_excel_btn = ttk.Button(import_export_frame, text="📥 Nhập Excel", command=self.import_from_excel)
        self.import_excel_btn.grid(row=0, column=0, sticky=tk.EW, padx=2) # Mở rộng Đông-Tây
        ToolTip(self.import_excel_btn, "Nhập dữ liệu email và kênh từ file Excel (.xlsx)")

        self.export_excel_btn = ttk.Button(import_export_frame, text="📤 Xuất Excel", command=self.export_to_excel)
        self.export_excel_btn.grid(row=0, column=1, sticky=tk.EW, padx=2) # Mở rộng Đông-Tây
        ToolTip(self.export_excel_btn, "Xuất dữ liệu hiện tại (đã giải mã) ra file Excel (.xlsx)")


        # Bảng điều khiển trung tâm (Tìm kiếm + Notebook Tabs)
        center_panel = ttk.Frame(main_frame)
        center_panel.grid(row=0, column=1, sticky="nsew", padx=(0, 10))
        center_panel.grid_rowconfigure(1, weight=1) # Hàng 1 (notebook) mở rộng theo chiều dọc
        center_panel.grid_columnconfigure(0, weight=1) # Cột 0 mở rộng theo chiều ngang

        # Bảng điều khiển Tìm kiếm
        search_panel = ttk.LabelFrame(center_panel, text="🔍 Tìm kiếm dữ liệu", padding="10")
        search_panel.grid(row=0, column=0, sticky=tk.EW, pady=(0, 10))
        search_panel.grid_columnconfigure(0, weight=1) # Frame nhập liệu tìm kiếm mở rộng

        # Frame nhập liệu Tìm kiếm (Entry + nút Clear)
        search_input_frame = ttk.Frame(search_panel)
        search_input_frame.grid(row=0, column=0, sticky=tk.EW)
        search_input_frame.columnconfigure(0, weight=1) # Trường nhập tìm kiếm mở rộng

        self.global_search_entry = ttk.Entry(search_input_frame, textvariable=self.global_search_var, width=40, font=self.entry_font)
        self.global_search_entry.grid(row=0, column=0, sticky=tk.EW, padx=(0, 5))
        ToolTip(self.global_search_entry, "Tìm kiếm trên toàn bộ dữ liệu (Ctrl+F để đặt focus)")
        self.clear_search_button = ttk.Button(search_input_frame, text="Xóa tìm", command=self.clear_search)
        self.clear_search_button.grid(row=0, column=1, sticky=tk.E, padx=(5, 0))
        ToolTip(self.clear_search_button, "Xóa kết quả tìm kiếm và trở về chế độ xem thông thường")

        # Nút radio Phạm vi Tìm kiếm và Checkbox Lọc
        scope_frame = ttk.Frame(search_panel)
        scope_frame.grid(row=1, column=0, sticky=tk.EW, pady=5)
        ttk.Label(scope_frame, text="Phạm vi:").pack(side=tk.LEFT, padx=(0, 5))
        ttk.Radiobutton(scope_frame, text="Tất cả", value="all", variable=self.search_scope, command=self.perform_global_search).pack(side=tk.LEFT, padx=5)
        ttk.Radiobutton(scope_frame, text="Emails", value="emails", variable=self.search_scope, command=self.perform_global_search).pack(side=tk.LEFT, padx=5)
        ttk.Radiobutton(scope_frame, text="Tên Kênh", value="names", variable=self.search_scope, command=self.perform_global_search).pack(side=tk.LEFT, padx=5)
        ttk.Radiobutton(scope_frame, text="URL Kênh", value="urls", variable=self.search_scope, command=self.perform_global_search).pack(side=tk.LEFT, padx=5)
        # === THÊM TÙY CHỌN PHẠM VI TÌM KIẾM MỚI ===
        ttk.Radiobutton(scope_frame, text="Ghi chú", value="notes", variable=self.search_scope, command=self.perform_global_search).pack(side=tk.LEFT, padx=5)
        ttk.Radiobutton(scope_frame, text="Vị trí ĐN", value="location", variable=self.search_scope, command=self.perform_global_search).pack(side=tk.LEFT, padx=5)
        ttk.Radiobutton(scope_frame, text="Người xác minh", value="verified_by", variable=self.search_scope, command=self.perform_global_search).pack(side=tk.LEFT, padx=5)
        ttk.Radiobutton(scope_frame, text="Điện thoại KH", value="recovery_phone", variable=self.search_scope, command=self.perform_global_search).pack(side=tk.LEFT, padx=5)

        ttk.Checkbutton(scope_frame, text="Chỉ kênh đang sử dụng", variable=self.filter_in_use).pack(side=tk.LEFT, padx=15)


        # Notebook (Các Tab)
        self.notebook = ttk.Notebook(center_panel)
        self.notebook.grid(row=1, column=0, sticky="nsew")

        # --- Tab 1: Chi tiết Email ---
        email_details_frame = ttk.Frame(self.notebook, padding="10")
        self.notebook.add(email_details_frame, text="Chi tiết Email")

        # Sử dụng PanedWindow để cho phép thay đổi kích thước giữa phần trên (form) và phần dưới (OTP, QR, Note)
        email_pane = tk.PanedWindow(email_details_frame, orient=tk.VERTICAL, sashrelief=tk.RAISED)
        email_pane.pack(fill=tk.BOTH, expand=True)

        # Frame cho các trường nhập liệu Email (phần trên của email_pane)
        email_form_top_frame = ttk.Frame(email_pane)
        email_pane.add(email_form_top_frame)
        email_form_top_frame.columnconfigure(1, weight=1) # Cho phép cột thứ hai (các trường nhập) mở rộng

        # Trường nhập Email
        ttk.Label(email_form_top_frame, text="Email:", font=self.label_font).grid(row=0, column=0, sticky=tk.W, pady=5, padx=(0, 10))
        # --- Thay đổi width và sticky cho Email Entry ---
        self.email_entry = ttk.Entry(email_form_top_frame, width=40, font=self.entry_font)
        self.email_entry.grid(row=0, column=1, sticky=tk.W, pady=5) # <-- Thay đổi sticky từ tk.EW sang tk.W
        ToolTip(self.email_entry, "Địa chỉ email cho tài khoản này")
        # Ràng buộc để reset style lỗi khi người dùng bắt đầu gõ hoặc focus
        self.email_entry.bind("<Key>", lambda e: self.email_entry.config(style='TEntry'))
        self.email_entry.bind("<FocusIn>", lambda e: self.email_entry.config(style='TEntry'))


        # Trường nhập Mật khẩu
        ttk.Label(email_form_top_frame, text="Mật khẩu:", font=self.label_font).grid(row=1, column=0, sticky=tk.W, pady=5, padx=(0, 10))

        # --- TẠO FRAME CHỨA PASSWORD ENTRY VÀ CHECKBUTTON ---
        password_input_frame = ttk.Frame(email_form_top_frame)
        # Đặt frame này vào cùng ô lưới với trường nhập mật khẩu (cột 1, hàng 1)
        password_input_frame.grid(row=1, column=1, sticky=tk.W, pady=5)
        # Cho phép các widget bên trong frame sắp xếp theo pack/grid... Ở đây dùng pack dễ hơn

        self.password_entry = ttk.Entry(password_input_frame, width=40, show="*", font=self.entry_font)
        # Đặt password_entry vào frame, căn trái (pack)
        self.password_entry.pack(side=tk.LEFT, fill=tk.X, expand=True, padx=(0, 5)) # Thêm padx để tạo khoảng trống giữa entry và checkbutton
        ToolTip(self.password_entry, "Mật khẩu cho tài khoản email này")

        # Checkbox hiển thị mật khẩu (Đặt vào cùng frame với password_entry)
        self.show_password_check = ttk.Checkbutton(password_input_frame, text="Hiện mật khẩu", variable=self.show_password, command=self.toggle_password_visibility)
        # Đặt show_password_check vào frame, ngay bên phải password_entry
        self.show_password_check.pack(side=tk.LEFT)
        # show_password_check không còn cần sticky tk.W hoặc padx riêng vì đã nằm trong frame

        # Trường nhập Email khôi phục
        ttk.Label(email_form_top_frame, text="Email khôi phục:", font=self.label_font).grid(row=2, column=0, sticky=tk.W, pady=5, padx=(0, 10))
        self.recovery_email_entry = ttk.Entry(email_form_top_frame, width=40, font=self.entry_font)
        self.recovery_email_entry.grid(row=2, column=1, sticky=tk.W, pady=5)
        ToolTip(self.recovery_email_entry, "Địa chỉ email khôi phục (nếu có)")
        self.recovery_email_entry.bind("<Key>", lambda e: self.recovery_email_entry.config(style='TEntry'))
        self.recovery_email_entry.bind("<FocusIn>", lambda e: self.recovery_email_entry.config(style='TEntry'))

        # === TRƯỜNG MẬT KHẨU EMAIL KHÔI PHỤC ===
        ttk.Label(email_form_top_frame, text="Mật khẩu Email khôi phục:", font=self.label_font).grid(row=3, column=0, sticky=tk.W, pady=5, padx=(0, 10))
        # --- Trường nhập này hiện không có checkbutton riêng đặt cạnh nó ---
        self.recovery_password_entry = ttk.Entry(email_form_top_frame, width=40, show="*", font=self.entry_font)
        self.recovery_password_entry.grid(row=3, column=1, sticky=tk.W, pady=5)
        ToolTip(self.recovery_password_entry, "Mật khẩu cho email khôi phục (nếu có)")
        self.recovery_password_entry.bind("<Key>", lambda e: self.recovery_password_entry.config(style='TEntry'))
        self.recovery_password_entry.bind("<FocusIn>", lambda e: self.recovery_password_entry.config(style='TEntry'))


        # === THÊM TRƯỜNG SỐ ĐIỆN THOẠI KHÔI PHỤC ===
        ttk.Label(email_form_top_frame, text="SĐT khôi phục:", font=self.label_font).grid(row=4, column=0, sticky=tk.W, pady=5, padx=(0, 10))
        # --- Thay đổi width và sticky cho Recovery Phone Entry ---
        self.recovery_phone_entry = ttk.Entry(email_form_top_frame, width=40, font=self.entry_font)
        self.recovery_phone_entry.grid(row=4, column=1, sticky=tk.W, pady=5) # <-- Thay đổi sticky từ tk.EW sang tk.W
        ToolTip(self.recovery_phone_entry, "Số điện thoại khôi phục (nếu có)")
        self.recovery_phone_entry.bind("<Key>", lambda e: self.recovery_phone_entry.config(style='TEntry'))
        self.recovery_phone_entry.bind("<FocusIn>", lambda e: self.recovery_phone_entry.config(style='TEntry'))


        # Trường nhập Khóa 2FA
        ttk.Label(email_form_top_frame, text="Khóa 2FA:", font=self.label_font).grid(row=5, column=0, sticky=tk.W, pady=5, padx=(0, 10))
        # --- Thay đổi width và sticky cho 2FA Key Entry ---
        self.key_entry = ttk.Entry(email_form_top_frame, width=40, font=self.entry_font)
        self.key_entry.grid(row=5, column=1, sticky=tk.W, pady=5) # <-- Thay đổi sticky từ tk.EW sang tk.W
        ToolTip(self.key_entry, "Khóa bí mật 2FA của Google Authenticator / TOTP (Base32)")
        # Ràng buộc để reset style lỗi khi người dùng bắt đầu gõ hoặc focus
        self.key_entry.bind("<Key>", lambda e: self.key_entry.config(style='TEntry'))
        self.key_entry.bind("<FocusIn>", lambda e: self.key_entry.config(style='TEntry'))


        # Trạng thái xác minh
        ttk.Label(email_form_top_frame, text="Trạng thái xác minh:", font=self.label_font).grid(row=6, column=0, sticky=tk.W, pady=5, padx=(0, 10))
        verified_status_frame = ttk.Frame(email_form_top_frame)
        # --- Thay đổi sticky cho Verified Status Frame ---
        verified_status_frame.grid(row=6, column=1, sticky=tk.W, pady=5) # <-- Thay đổi sticky từ tk.W (đã đúng) -> giữ nguyên
        self.is_verified_checkbox = ttk.Checkbutton(
            verified_status_frame, text="Đã xác minh", variable=self.is_verified_var
        )
        self.is_verified_checkbox.pack(side=tk.LEFT, padx=(0, 10))
        ToolTip(self.is_verified_checkbox, "Chọn nếu tài khoản email này đã được xác minh thành công")

        self.verification_failed_checkbox = ttk.Checkbutton(
             verified_status_frame, text="Xác minh bị lỗi / từ chối", variable=self.verification_failed_var
        )
        self.verification_failed_checkbox.pack(side=tk.LEFT)
        ToolTip(self.verification_failed_checkbox, "Chọn nếu các lần xác minh cho email này đã thất bại hoặc bị từ chối")


        # Trường nhập Người xác minh
        ttk.Label(email_form_top_frame, text="Người xác minh:", font=self.label_font).grid(row=7, column=0, sticky=tk.W, pady=5, padx=(0, 10))
        # --- Thay đổi width và sticky cho Verified By Entry ---
        self.verified_by_entry = ttk.Entry(email_form_top_frame, width=40, font=self.entry_font, textvariable=self.verified_by_var)
        self.verified_by_entry.grid(row=7, column=1, sticky=tk.W, pady=5) # <-- Thay đổi sticky từ tk.EW sang tk.W
        ToolTip(self.verified_by_entry, "Tên hoặc mã định danh của người đã xử lý việc xác minh")

        # Trường nhập Vị trí đăng nhập
        ttk.Label(email_form_top_frame, text="Đăng nhập ở:", font=self.label_font).grid(row=8, column=0, sticky=tk.W, pady=5, padx=(0, 10))
        # --- Thay đổi width và sticky cho Login Location Entry ---
        self.login_location_entry = ttk.Entry(email_form_top_frame, width=40, font=self.entry_font, textvariable=self.login_location_var)
        self.login_location_entry.grid(row=8, column=1, sticky=tk.W, pady=5) # <-- Thay đổi sticky từ tk.EW sang tk.W
        ToolTip(self.login_location_entry, "Vị trí đăng nhập thông thường (ví dụ: Quốc gia, Thành phố, tên VPN)")

        # Nút Lưu Email
        self.save_email_button = ttk.Button(email_form_top_frame, text="💾 Lưu Email", command=self.save_email, style='Accent.TButton')
        # Điều chỉnh grid row
        # --- Thay đổi sticky cho Save Email Button ---
        self.save_email_button.grid(row=9, column=1, sticky=tk.W, pady=10) # <-- Thay đổi sticky từ tk.W (đã đúng) -> giữ nguyên
        ToolTip(self.save_email_button, "Lưu thông tin email (Ctrl+S)")

        # Frame cho phần dưới của email_pane (OTP, QR, Note)
        email_form_bottom_frame = ttk.Frame(email_pane)
        email_pane.add(email_form_bottom_frame)
        email_form_bottom_frame.grid_columnconfigure(0, weight=1) # Cho phép các khung con mở rộng theo chiều ngang

        # Frame Trình tạo OTP
        otp_frame = ttk.LabelFrame(email_form_bottom_frame, text="Trình tạo OTP", padding="10")
        otp_frame.grid(row=0, column=0, sticky=tk.EW, pady=(0, 10))
        otp_frame.grid_columnconfigure(1, weight=1) # Cho phép frame hiển thị OTP mở rộng

        # Canvas tiến trình OTP
        self.otp_canvas = tk.Canvas(otp_frame, width=100, height=100, highlightthickness=0)
        self.otp_canvas.grid(row=0, column=0, padx=(0, 10), sticky=tk.N)
        # Vòng cung và hình oval cho chỉ báo tiến trình
        self.otp_arc = self.otp_canvas.create_arc(10, 10, 90, 90, start=90, extent=360, outline='#3498db', width=5, style=tk.ARC)
        self.otp_canvas.create_oval(15, 15, 85, 85, outline='#bdc3c7', width=2) # Vòng tròn ngoài
        # === CẬP NHẬT FONT CHO TEXT ITEM TRÊN CANVAS ===
        self.otp_timer_text_item = self.otp_canvas.create_text(50, 50, text="", font=('Arial', 16, 'bold'), fill='black', anchor=tk.CENTER) # Căn giữa (50,50), font to hơn


        # Frame hiển thị và sao chép OTP
        otp_display_frame = ttk.Frame(otp_frame)
        otp_display_frame.grid(row=0, column=1, sticky=tk.NSEW)
        # === CẬP NHẬT FONT CHO OTP LABEL ===
        self.otp_label = ttk.Label(otp_display_frame, text="------", font=("Courier", 36, "bold"), foreground="gray") # Cỡ chữ to hơn
        self.otp_label.pack(pady=(0, 5))
        # self.otp_time_label = ttk.Label(otp_display_frame, text="", foreground="gray") # Xóa widget này
        # self.otp_time_label.pack(pady=(5, 5)) # Xóa pack cho widget này

        self.copy_otp_button = ttk.Button(otp_display_frame, text="📋 Sao chép OTP", command=self.copy_otp)
        self.copy_otp_button.pack(pady=(5, 0))
        ToolTip(self.copy_otp_button, "Sao chép mã OTP hiện tại vào clipboard")

        # Frame Mã QR 2FA
        qr_frame = ttk.LabelFrame(email_form_bottom_frame, text="Mã QR 2FA", padding="10")
        qr_frame.grid(row=1, column=0, sticky=tk.EW, pady=(0, 10))
        qr_frame.grid_columnconfigure(1, weight=1) # Cho phép nhãn ảnh mở rộng

        # Frame Nút QR Code
        qr_button_frame = ttk.Frame(qr_frame)
        qr_button_frame.grid(row=0, column=0, sticky=tk.W, padx=(0, 10))
        self.load_qr_button = ttk.Button(qr_button_frame, text="🖼️ Tải ảnh...", command=self.load_qrcode_image, state=tk.NORMAL if HAS_QR_LIBS else tk.DISABLED)
        self.load_qr_button.pack(side=tk.LEFT, padx=2)
        ToolTip(self.load_qr_button, "Tải một file ảnh mã QR")
        self.scan_qr_button = ttk.Button(qr_button_frame, text="🔍 Quét ảnh...", command=self.scan_qrcode_image, state=tk.NORMAL if HAS_QR_LIBS else tk.DISABLED)
        self.scan_qr_button.pack(side=tk.LEFT, padx=2)
        ToolTip(self.scan_qr_button, "Quét file ảnh để tìm khóa 2FA")
        self.clear_qr_button = ttk.Button(qr_button_frame, text="❌ Xóa ảnh", command=self.clear_qrcode_image)
        self.clear_qr_button.pack(side=tk.LEFT, padx=2)
        ToolTip(self.clear_qr_button, "Xóa ảnh QR đang lưu")

        # Nhãn xem trước ảnh mã QR
        self.qrcode_image_label = ttk.Label(qr_frame, text="Chưa lưu ảnh mã QR nào", compound=tk.TOP, anchor=tk.CENTER)
        self.qrcode_image_label.grid(row=0, column=1, sticky=tk.EW)

        # Frame Ghi chú Email (trường mới)
        email_note_frame = ttk.LabelFrame(email_form_bottom_frame, text="Ghi chú Email", padding="10")
        email_note_frame.grid(row=2, column=0, sticky=tk.NSEW, pady=(0, 5)) # Mở rộng theo cả 4 hướng
        email_note_frame.grid_rowconfigure(0, weight=1) # Vùng văn bản mở rộng
        email_note_frame.grid_columnconfigure(0, weight=1) # Vùng văn bản mở rộng

        self.email_note_text = tk.Text(email_note_frame, height=5, wrap=tk.WORD, font=self.text_font)
        self.email_note_text.grid(row=0, column=0, sticky=tk.NSEW)
        ToolTip(self.email_note_text, "Các ghi chú bổ sung về tài khoản email này")

        email_note_scrollbar = ttk.Scrollbar(email_note_frame, command=self.email_note_text.yview)
        email_note_scrollbar.grid(row=0, column=1, sticky=tk.NS)
        self.email_note_text.config(yscrollcommand=email_note_scrollbar.set)


        # --- Tab 2: Quản lý Kênh ---
        channel_frame = ttk.Frame(self.notebook, padding="10")
        self.notebook.add(channel_frame, text="Quản lý Kênh")

        # Frame Biểu mẫu Kênh
        channel_form_frame = ttk.Frame(channel_frame)
        channel_form_frame.pack(fill=tk.X, pady=5)
        channel_form_frame.columnconfigure(1, weight=1) # Cho phép trường nhập mở rộng

        # Trường nhập URL Kênh
        ttk.Label(channel_form_frame, text="URL Kênh:", font=self.label_font).grid(row=0, column=0, sticky=tk.W, pady=5, padx=(0, 10))
        # --- Thay đổi width và sticky cho Channel URL Entry ---
        self.url_entry = ttk.Entry(channel_form_frame, width=40, font=self.entry_font)
        self.url_entry.grid(row=0, column=1, sticky=tk.W, pady=5) # <-- Thay đổi sticky từ tk.EW sang tk.W
        ToolTip(self.url_entry, "URL đầy đủ của kênh YouTube (ví dụ: https://www.youtube.com/@tenkenh)")
        # Ràng buộc để reset style lỗi khi người dùng bắt đầu gõ hoặc focus
        self.url_entry.bind("<Key>", lambda e: self.url_entry.config(style='TEntry'))
        self.url_entry.bind("<FocusIn>", lambda e: self.url_entry.config(style='TEntry'))

        # Trường nhập Tên Kênh
        ttk.Label(channel_form_frame, text="Tên Kênh:", font=self.label_font).grid(row=1, column=0, sticky=tk.W, pady=5, padx=(0, 10))
        # --- Thay đổi width và sticky cho Channel Name Entry ---
        self.name_entry = ttk.Entry(channel_form_frame, width=40, font=self.entry_font)
        self.name_entry.grid(row=1, column=1, sticky=tk.W, pady=5) # <-- Thay đổi sticky từ tk.EW sang tk.W
        ToolTip(self.name_entry, "Tên của kênh YouTube")

        # Trường nhập Ghi chú Kênh
        ttk.Label(channel_form_frame, text="Ghi chú:", font=self.label_font).grid(row=2, column=0, sticky=tk.W, pady=5, padx=(0, 10))
        # --- Thay đổi width và sticky cho Channel Note Entry ---
        self.note_entry = ttk.Entry(channel_form_frame, width=40, font=self.entry_font)
        self.note_entry.grid(row=2, column=1, sticky=tk.W, pady=5) # <-- Thay đổi sticky từ tk.EW sang tk.W
        ToolTip(self.note_entry, "Bất kỳ ghi chú nào liên quan đến kênh này")

        # Checkbox Kênh đang sử dụng
        self.use_var = tk.BooleanVar()
        self.use_checkbox = ttk.Checkbutton(channel_form_frame, text="Đang sử dụng", variable=self.use_var)
        # --- Thay đổi sticky cho Channel In Use Checkbox ---
        self.use_checkbox.grid(row=3, column=1, sticky=tk.W, pady=5) # <-- sticky đã là tk.W, giữ nguyên
        ToolTip(self.use_checkbox, "Chọn nếu kênh này hiện đang hoạt động hoặc được sử dụng")


        # Frame Nút Biểu mẫu Kênh (Lấy tên, Lưu)
        button_frame = ttk.Frame(channel_form_frame)
        # --- Thay đổi sticky cho Channel Button Frame ---
        button_frame.grid(row=4, column=1, sticky=tk.W, pady=5) # <-- sticky đã là tk.W, giữ nguyên
        # Nội dung bên trong button_frame (các nút) sẽ được căn trái (sticky=tk.LEFT)
        self.fetch_name_button = ttk.Button(button_frame, text="🌐 Lấy tên", command=self.fetch_channel_name)
        self.fetch_name_button.pack(side=tk.LEFT, padx=(0, 5))
        ToolTip(self.fetch_name_button, "Thử tự động lấy tên kênh từ URL")
        self.save_channel_button = ttk.Button(button_frame, text="💾 Lưu Kênh", command=self.save_channel, style='Accent.TButton')
        self.save_channel_button.pack(side=tk.LEFT, padx=5)
        ToolTip(self.save_channel_button, "Lưu thông tin kênh")

        # Frame Danh sách Kênh (Treeview)
        list_frame = ttk.LabelFrame(channel_frame, text="Danh sách Kênh", padding="5")
        list_frame.pack(fill=tk.BOTH, expand=True, pady=10)
        list_frame.grid_rowconfigure(1, weight=1) # Hàng 1 (treeview kênh) mở rộng theo chiều dọc
        list_frame.grid_columnconfigure(0, weight=1) # Cột 0 (nội dung danh sách kênh) mở rộng

        # Các nút Danh sách Kênh (Thêm, Xóa, Sao chép URL)
        channel_buttons = ttk.Frame(list_frame)
        channel_buttons.grid(row=0, column=0, sticky=tk.EW, pady=5)
        channel_buttons.columnconfigure(0, weight=1); channel_buttons.columnconfigure(1, weight=1); channel_buttons.columnconfigure(2, weight=1) # Phân phối không gian

        self.add_channel_button = ttk.Button(channel_buttons, text="➕ Thêm Kênh", command=self.add_channel)
        self.add_channel_button.grid(row=0, column=0, sticky=tk.W, padx=2)
        ToolTip(self.add_channel_button, "Thêm một mục kênh mới vào danh sách cho email đang chọn")
        self.delete_channel_button = ttk.Button(channel_buttons, text="🗑 Xóa Kênh", command=self.delete_channel)
        self.delete_channel_button.grid(row=0, column=1, padx=2) # Căn giữa
        ToolTip(self.delete_channel_button, "Xóa kênh đang chọn khỏi danh sách")
        self.copy_channel_url_button = ttk.Button(channel_buttons, text="📋 Sao chép URL", command=self.copy_channel_url)
        self.copy_channel_url_button.grid(row=0, column=2, sticky=tk.E, padx=2)
        ToolTip(self.copy_channel_url_button, "Sao chép URL của kênh đang chọn từ danh sách")

        # Treeview Danh sách Kênh
        channel_list_frame = ttk.Frame(list_frame)
        channel_list_frame.grid(row=1, column=0, sticky="nsew", pady=5)
        channel_list_frame.grid_rowconfigure(0, weight=1)
        channel_list_frame.grid_columnconfigure(0, weight=1)

        self.channel_tree = ttk.Treeview(channel_list_frame, columns=('status', 'name', 'url', 'note'), show='headings', height=12)
        # Định nghĩa tiêu đề và liên kết chúng với các phương thức sắp xếp
        self.channel_tree.heading('status', text='Trạng thái', anchor=tk.W, command=lambda: self._sort_channel_tree('status'))
        self.channel_tree.heading('name', text='Tên Kênh', anchor=tk.W, command=lambda: self._sort_channel_tree('name'))
        self.channel_tree.heading('url', text='URL', anchor=tk.W, command=lambda: self._sort_channel_tree('url'))
        self.channel_tree.heading('note', text='Ghi chú', anchor=tk.W, command=lambda: self._sort_channel_tree('note'))
        # Định nghĩa thuộc tính cột
        self.channel_tree.column('status', width=70, stretch=tk.NO, anchor=tk.CENTER)
        self.channel_tree.column('name', width=200, stretch=tk.YES)
        self.channel_tree.column('url', width=250, stretch=tk.YES)
        self.channel_tree.column('note', width=200, stretch=tk.YES)
        # Đặt Treeview và ràng buộc sự kiện chọn
        self.channel_tree.grid(row=0, column=0, sticky="nsew")
        self.channel_tree.bind("<<TreeviewSelect>>", self.on_channel_select)

        # Thanh cuộn cho Treeview Kênh
        channel_scrollbar_y = ttk.Scrollbar(channel_list_frame, orient=tk.VERTICAL, command=self.channel_tree.yview)
        channel_scrollbar_y.grid(row=0, column=1, sticky="ns")
        self.channel_tree.configure(yscrollcommand=channel_scrollbar_y.set)

        channel_scrollbar_x = ttk.Scrollbar(list_frame, orient=tk.HORIZONTAL, command=self.channel_tree.xview)
        channel_scrollbar_x.grid(row=2, column=0, sticky="ew") # Đặt dưới channel_list_frame
        self.channel_tree.configure(xscrollcommand=channel_scrollbar_x.set)


        # Bảng điều khiển bên phải (Xem nhanh)
        right_panel = ttk.LabelFrame(main_frame, text="Xem nhanh Kênh", padding="10")
        right_panel.grid(row=0, column=2, sticky="nsew")
        right_panel.grid_rowconfigure(0, weight=1) # Vùng văn bản mở rộng theo chiều dọc
        right_panel.grid_columnconfigure(0, weight=1) # Vùng văn bản mở rộng theo chiều ngang

        self.quick_view_frame = ttk.Frame(right_panel)
        self.quick_view_frame.grid(row=0, column=0, sticky="nsew")
        self.quick_view_frame.grid_rowconfigure(0, weight=1)
        self.quick_view_frame.grid_columnconfigure(0, weight=1)

        # Vùng văn bản Thông tin Kênh (chỉ đọc)
        self.channel_info_text = tk.Text(self.quick_view_frame, width=40, height=30, wrap=tk.WORD,
                                       font=('Arial', 9), padx=5, pady=5,
                                       state=tk.DISABLED, background=self.root.cget('bg')) # Đặt nền trùng với cửa sổ
        self.channel_info_text.grid(row=0, column=0, sticky="nsew")

        # Thanh cuộn cho Vùng văn bản Xem nhanh
        channel_info_scrollbar = ttk.Scrollbar(self.quick_view_frame, command=self.channel_info_text.yview)
        channel_info_scrollbar.grid(row=0, column=1, sticky="ns")
        self.channel_info_text.configure(yscrollcommand=channel_info_scrollbar.set)

        # Cấu hình tag để tạo kiểu cho văn bản trong xem nhanh
        self.channel_info_text.tag_configure("title", font=('Arial', 10, 'bold'), foreground="#2c3e50")
        self.channel_info_text.tag_configure("url", foreground="#3498db", underline=True)
        self.channel_info_text.tag_configure("in_use", foreground="#27ae60") # Xanh lá
        self.channel_info_text.tag_configure("not_in_use", foreground="#e74c3c") # Đỏ cho 'Không sử dụng' và 'Chưa xác minh'
        self.channel_info_text.tag_configure("verified", font=('Arial', 9, 'bold'), foreground="blue") # Xanh dương đậm cho 'Đã xác minh'
        self.channel_info_text.tag_configure("failed", font=('Arial', 9, 'bold'), foreground="red") # Đỏ đậm cho 'Xác minh thất bại'
        self.channel_info_text.tag_configure("note", font=('Arial', 9, 'italic'), foreground="#556b2f") # Xanh rêu đậm cho Ghi chú
        # === THÊM TAG CHO TRƯỜNG MỚI TRONG XEM NHANH ===
        self.channel_info_text.tag_configure("recovery_info", foreground="#808080") # Màu xám cho thông tin khôi phục


        # Frame Nút Xem nhanh
        channel_info_buttons = ttk.Frame(right_panel)
        channel_info_buttons.grid(row=1, column=0, sticky=tk.EW, pady=(10, 0))
        channel_info_buttons.columnconfigure(0, weight=1) # Phân phối không gian
        channel_info_buttons.columnconfigure(1, weight=1)

        self.copy_url_button = ttk.Button(channel_info_buttons, text="📋 Sao chép URL", command=self.copy_selected_channel_url)
        self.copy_url_button.grid(row=0, column=0, sticky=tk.E, padx=2) # Dính về phía Đông
        ToolTip(self.copy_url_button, "Sao chép URL kênh từ phần xem nhanh")

        self.refresh_button = ttk.Button(channel_info_buttons, text="🔄 Làm mới", command=self.refresh_channel_quick_view)
        self.refresh_button.grid(row=0, column=1, sticky=tk.W, padx=2) # Dính về phía Tây
        ToolTip(self.refresh_button, "Làm mới nội dung xem nhanh kênh")


        # Thanh trạng thái ở cuối cửa sổ chính
        self.status_var = tk.StringVar(value="Sẵn sàng")
        self.status_bar = ttk.Label(self.root, textvariable=self.status_var, relief=tk.SUNKEN, anchor=tk.W)
        self.status_bar.pack(side=tk.BOTTOM, fill=tk.X)

        # Thêm một label cho trạng thái auto-lock
        self.auto_lock_status_var = tk.StringVar(value="")
        if AUTO_LOCK_TIMEOUT_MS is not None and AUTO_LOCK_TIMEOUT_MS > 0:
            timeout_minutes = AUTO_LOCK_TIMEOUT_MS // 60000
            self.auto_lock_status_var.set(f"Tự động khóa sau {timeout_minutes} phút không hoạt động.")

        self.auto_lock_status_bar = ttk.Label(self.root, textvariable=self.auto_lock_status_var, anchor=tk.E)
        self.auto_lock_status_bar.pack(side=tk.BOTTOM, fill=tk.X) # Đặt nó dưới thanh trạng thái chính

    # --- Phương thức Sắp xếp ---
    def _sort_email_tree(self, col):
        """Sắp xếp treeview email theo cột được chỉ định."""
        # Ngăn chặn sắp xếp nếu đang ở chế độ xem kết quả tìm kiếm hoặc bị khóa
        if self.current_view == 'search' or self._is_locked:
             self.status_var.set("Không thể sắp xếp trong chế độ tìm kiếm hoặc khi bị khóa.")
             return

        # Xác định thứ tự sắp xếp (đảo ngược thứ tự hiện tại)
        if self._email_sort_col == col:
            self._email_sort_order = not self._email_sort_order
        else:
            self._email_sort_col = col # Đặt cột sắp xếp mới
            self._email_sort_order = False # Mặc định là tăng dần

        # Định nghĩa hàm khóa để sắp xếp
        def sort_key(item):
            if col == 'email':
                # Sắp xếp email không phân biệt chữ hoa chữ thường
                return item.get('email', '').lower()
            elif col == 'channel_count':
                # Sắp xếp theo số lượng kênh, xử lý trường hợp danh sách kênh là None
                channels = item.get('channels', [])
                return len(channels) if channels is not None else 0
            return "" # Trả về mặc định cho các cột không mong muốn

        # Sắp xếp danh sách dữ liệu gốc
        self.data.sort(key=sort_key, reverse=self._email_sort_order)

        # Cập nhật tiêu đề treeview để hiển thị mũi tên sắp xếp
        for c in ('email', 'channel_count'):
            heading_text = 'Email' if c == 'email' else 'Kênh'
            current_text = self.email_tree.heading(c, 'text')
            clean_text = current_text.replace(' ▲', '').replace(' ▼', '') # Xóa các mũi tên hiện có

            if c == col:
                arrow = ' ▼' if self._email_sort_order else ' ▲' # Thêm mũi tên cho cột sắp xếp hiện tại
                self.email_tree.heading(c, text=f"{clean_text}{arrow}")
            else:
                self.email_tree.heading(c, text=clean_text) # Xóa mũi tên khỏi các cột khác

        # Làm mới hiển thị treeview với dữ liệu đã sắp xếp
        self.refresh_email_list()

        # Xóa lựa chọn và chi tiết sau khi sắp xếp
        self.selected_email_index = None
        self.selected_channel_index = None
        self.clear_email_details()
        self.clear_channel_details()
        self.channel_tree.delete(*self.channel_tree.get_children()) # Xóa treeview danh sách kênh
        self.update_channel_quick_view([]) # Xóa xem nhanh

        # Cập nhật thanh trạng thái
        sort_order_str = 'giảm dần' if self._email_sort_order else 'tăng dần'
        self.status_var.set(f"Email đã được sắp xếp theo {col.replace('_', ' ')} {sort_order_str}")


    def _sort_channel_tree(self, col):
        """Sắp xếp treeview kênh theo cột được chỉ định cho email đang chọn."""
        # Kiểm tra xem có email nào được chọn không và không ở chế độ tìm kiếm hoặc bị khóa
        if self.selected_email_index is None or not (0 <= self.selected_email_index < len(self.data)) or self.current_view == 'search' or self._is_locked:
             self.status_var.set("Chọn một email ở chế độ xem thông thường để sắp xếp kênh.")
             return

        # Xác định thứ tự sắp xếp (đảo ngược thứ tự hiện tại)
        if self._channel_sort_col == col:
            self._channel_sort_order = not self._channel_sort_order
        else:
            self._channel_sort_col = col # Đặt cột sắp xếp mới
            self._channel_sort_order = False # Mặc định là tăng dần

        # Lấy danh sách kênh cho email đang chọn
        channels = self.data[self.selected_email_index].get('channels', [])
        if channels is None: channels = [] # Đảm bảo là một danh sách

        # Định nghĩa hàm khóa để sắp xếp kênh
        def sort_key(channel):
            if col == 'status':
                 # Sắp xếp boolean (False đứng trước True theo mặc định, nên ❌ trước ✅)
                 return channel.get('in_use', False)
            elif col == 'name':
                 # Sắp xếp tên không phân biệt chữ hoa chữ thường
                 return channel.get('channel_name', '').lower()
            elif col == 'url':
                 # Sắp xếp URL không phân biệt chữ hoa chữ thường
                 return channel.get('channel_url', '').lower()
            elif col == 'note':
                 # Sắp xếp ghi chú không phân biệt chữ hoa chữ thường
                 return channel.get('note', '').lower()
            return "" # Trả về mặc định

        # Sắp xếp danh sách kênh TẠI CHỖ
        channels.sort(key=sort_key, reverse=self._channel_sort_order)

        # Cập nhật tiêu đề treeview kênh để hiển thị mũi tên sắp xếp
        for c in ('status', 'name', 'url', 'note'):
            heading_text = c.replace('_', ' ').title()
            if c == 'status': heading_text = 'Trạng thái' # Trường hợp đặc biệt cho tiêu đề cột trạng thái
            current_text = self.channel_tree.heading(c, 'text')
            clean_text = current_text.replace(' ▲', '').replace(' ▼', '') # Xóa các mũi tên hiện có

            if c == col:
                arrow = ' ▼' if self._channel_sort_order else ' ▲' # Thêm mũi tên cho cột sắp xếp hiện tại
                self.channel_tree.heading(c, text=f"{clean_text}{arrow}")
            else:
                self.channel_tree.heading(c, text=clean_text) # Xóa mũi tên khỏi các cột khác


        # Cập nhật hiển thị treeview kênh với danh sách đã sắp xếp
        self.update_channel_list() # Hàm này sẽ điền lại treeview từ self.data[selected_email_index]['channels']

        # Xóa chi tiết kênh đang chọn sau khi sắp xếp danh sách
        self.selected_channel_index = None
        self.clear_channel_details()

        # Cập nhật thanh trạng thái
        sort_order_str = 'giảm dần' if self._channel_sort_order else 'tăng dần'
        self.status_var.set(f"Kênh đã được sắp xếp theo {col.replace('_', ' ')} {sort_order_str}")


    # --- Phương thức Xử lý Sự kiện Giao diện và Hành động ---
    def on_closing(self):
        """Xử lý sự kiện đóng cửa sổ, nhắc nhở lưu nếu dữ liệu đã thay đổi."""
        # Hủy kiểm tra tự động khóa khi đóng
        if self._auto_lock_job:
            self.root.after_cancel(self._auto_lock_job)
            self._auto_lock_job = None

        if self._data_changed:
            response = messagebox.askyesnocancel("Thay đổi chưa lưu", "Bạn có thay đổi chưa lưu. Bạn có muốn lưu trước khi đóng không?", parent=self.root)
            if response is True:
                self._save_data()
                # Chờ một chút trước khi đóng để đảm bảo thao tác lưu hoàn tất
                # Kiểm tra lại _data_changed để đảm bảo lưu thành công
                if not self._data_changed:
                     self.root.after(100, self._perform_close)
                # Nếu lưu thất bại (_data_changed vẫn là True), không đóng ngay lập tức
            elif response is False:
                self._perform_close() # Đóng mà không lưu
            # Ngược lại (response là None cho Hủy): Không làm gì, cửa sổ vẫn mở
        else:
            self._perform_close() # Đóng trực tiếp nếu không có thay đổi chưa lưu

    def _perform_close(self):
        """Dọn dẹp và hủy cửa sổ chính."""
        print("Đang đóng ứng dụng...")
        self.otp_thread_id = None # Ra hiệu cho luồng OTP dừng lại
        # Kiểm tra xem cửa sổ root còn tồn tại không trước khi hủy
        if self.root and self.root.winfo_exists():
            self.root.destroy()

    def save_current_tab(self, event=None):
        """Lưu dữ liệu từ tab notebook hiện tại (Email hoặc Kênh)."""
        # Kiểm tra xem ứng dụng có bị khóa không
        if self._is_locked:
            self.status_var.set("Ứng dụng đang bị khóa. Không thể lưu.")
            return

        # Kiểm tra xem widget notebook có tồn tại không và cửa sổ root hợp lệ không
        if not hasattr(self, 'notebook') or not self.notebook.winfo_exists() or not self.root or not self.root.winfo_exists():
            return

        try:
            # Lấy chỉ mục của tab đang được chọn
            selected_tab_index = self.notebook.index(self.notebook.select())

            # Gọi phương thức lưu phù hợp dựa trên tab đã chọn
            if selected_tab_index == 0: # Tab Chi tiết Email
                self.save_email()
            elif selected_tab_index == 1: # Tab Quản lý Kênh
                self.save_channel()
        except tk.TclError:
            # Bắt các lỗi Tcl tiềm ẩn nếu các widget đang bị hủy trong khi gọi hàm này
            pass

    def toggle_password_visibility(self):
        """Bật/tắt hiển thị mật khẩu trong trường nhập mật khẩu."""
        # Thay đổi thuộc tính 'show' của widget nhập liệu dựa trên biến checkbox
        show_char = "" if self.show_password.get() else "*"
        self.password_entry.config(show=show_char)
        # === ÁP DỤNG CHO CẢ TRƯỜNG MẬT KHẨU KHÔI PHỤC ===
        self.recovery_password_entry.config(show=show_char)


    def copy_selected_channel_url(self):
        """Sao chép URL của kênh hiện đang hiển thị trong Bảng xem nhanh vào clipboard."""
         # Kiểm tra xem ứng dụng có bị khóa không
        if self._is_locked:
            self.status_var.set("Ứng dụng đang bị khóa. Không thể sao chép.")
            return

        # Bảng xem nhanh hiển thị các kênh từ danh sách current_channels,
        # danh sách này có thể đã được lọc (ví dụ: theo tìm kiếm).
        if not self.current_channels:
            messagebox.showwarning("Không có kênh", "Không có kênh nào trong bảng xem nhanh để sao chép URL.", parent=self.root)
            return

        # If there's only one channel in the quick view, copy its URL directly
        if len(self.current_channels) == 1:
            url = self.current_channels[0].get("channel_url", "")
            if url:
                 pyperclip.copy(url)
                 self.status_var.set(f"Đã sao chép URL: {url}")
            else:
                 messagebox.showwarning("Lỗi", "Không tìm thấy URL kênh trong kênh đã chọn.", parent=self.root)
            return

        # If there are multiple channels in the quick view (e.g., after search),
        # open a dialog to let the user pick which URL to copy.
        dialog = tk.Toplevel(self.root)
        dialog.title("Chọn Kênh để Sao chép URL")
        dialog.transient(self.root) # Đặt hộp thoại luôn ở trên cửa sổ chính
        dialog.grab_set() # Biến hộp thoại thành modal (chặn tương tác với cửa sổ chính)

        ttk.Label(dialog, text="Chọn một URL kênh để sao chép:", padding=5).pack(pady=10)

        list_frame = ttk.Frame(dialog, padding=5)
        list_frame.pack(fill=tk.BOTH, expand=True, padx=10)
        list_frame.grid_rowconfigure(0, weight=1)
        list_frame.grid_columnconfigure(0, weight=1)

        scrollbar = ttk.Scrollbar(list_frame)
        scrollbar.grid(row=0, column=1, sticky="ns")

        listbox = tk.Listbox(list_frame, yscrollcommand=scrollbar.set, font=('Arial', 9))
        listbox.grid(row=0, column=0, sticky="nsew")
        scrollbar.config(command=listbox.yview)

        # Fill the listbox with channels from the quick view list
        for i, ch in enumerate(self.current_channels):
            name = ch.get('channel_name', 'Không tên')
            url = ch.get('channel_url', 'Không có URL')
            listbox.insert(tk.END, f"{i+1}. {name} - {url}")

        def on_select():
            """Handles selection from the listbox and copies the URL."""
            sel = listbox.curselection()
            if not sel:
                messagebox.showwarning("Yêu cầu chọn", "Vui lòng chọn một kênh từ danh sách.", parent=dialog)
                return

            idx = sel[0] # Get the index of the selected item

            if 0 <= idx < len(self.current_channels):
                url = self.current_channels[idx].get("channel_url", "")
                if url:
                     pyperclip.copy(url)
                     self.status_var.set(f"Đã sao chép URL: {url}")
                     dialog.destroy() # Close the dialog on success
                else:
                     messagebox.showwarning("Lỗi", "Không tìm thấy URL kênh cho mục đã chọn.", parent=dialog)
            else:
                 messagebox.showerror("Lỗi", "Chỉ mục lựa chọn không hợp lệ.", parent=dialog)

        # Frame for dialog buttons
        button_frame = ttk.Frame(dialog, padding=5)
        button_frame.pack(fill=tk.X, pady=10)
        button_frame.columnconfigure(0, weight=1)
        button_frame.columnconfigure(1, weight=1)

        ttk.Button(button_frame, text="Sao chép URL", command=on_select).pack(side=tk.LEFT, expand=True, padx=5)
        ttk.Button(button_frame, text="Hủy", command=dialog.destroy).pack(side=tk.RIGHT, expand=True, padx=5)

        # Center the dialog relative to the parent window
        self._center_dialog_relative_to_parent(dialog, self.root)


    def _center_dialog_relative_to_parent(self, dialog, parent):
        """Căn giữa một cửa sổ dialog cho trước so với cửa sổ parent."""
        # Kiểm tra xem parent có tồn tại không
        if not parent or not parent.winfo_exists():
             print("Cảnh báo: Không thể căn giữa dialog, cửa sổ cha không tồn tại.")
             # Căn giữa trên màn hình nếu không có parent
             dialog.update_idletasks()
             dialog_width = dialog.winfo_reqwidth()
             dialog_height = dialog.winfo_reqheight()
             screen_width = dialog.winfo_screenwidth()
             screen_height = dialog.winfo_screenheight()
             x = (screen_width // 2) - (dialog_width // 2)
             y = (screen_height // 2) - (dialog_height // 2)
             dialog.geometry(f"+{x}+{y}")
             return

        dialog.update_idletasks()

        dialog_width = dialog.winfo_reqwidth()
        dialog_height = dialog.winfo_reqheight()

        parent_x = parent.winfo_x()
        parent_y = parent.winfo_y()
        parent_width = parent.winfo_width()
        parent_height = parent.winfo_height()

        x = parent_x + (parent_width // 2) - (dialog_width // 2)
        y = parent_y + (parent_height // 2) - (dialog_height // 2)

        dialog.geometry(f"+{x}+{y}")


    def refresh_channel_quick_view(self):
        """Làm mới nội dung hiển thị trong bảng Xem nhanh Kênh."""
        # Kiểm tra xem ứng dụng có bị khóa không
        if self._is_locked:
            self.status_var.set("Ứng dụng đang bị khóa. Không thể làm mới xem nhanh.")
            self.update_channel_quick_view([]) # Xóa xem nhanh khi bị khóa
            return

        # Kiểm tra xem có email nào được chọn không
        if self.selected_email_index is None or not (0 <= self.selected_email_index < len(self.data)):
            self.update_channel_quick_view([]) # Xóa xem nhanh nếu không có email nào được chọn
            self.status_var.set("Chưa chọn email để xem nhanh")
            return

        channels_to_display = []
        if self.current_view == "search":
             # Ở chế độ tìm kiếm, xem nhanh nên hiển thị các kênh khớp với tìm kiếm cho email đã chọn
             search_result = next((sr for sr in self.search_results if sr["email_idx"] == self.selected_email_index), None)
             if search_result:
                 # Trích xuất dữ liệu kênh từ các kết quả khớp tìm kiếm cho email này
                 channels_to_display = [ch for _, ch in search_result["channel_matches"]]
             email_addr = self.data[self.selected_email_index].get('email', 'đã chọn')
             self.status_var.set(f"Đã làm mới xem nhanh cho {len(channels_to_display)} kết quả tìm kiếm trong {email_addr}")
        else: # Chế độ xem thông thường
            # Ở chế độ xem thông thường, xem nhanh hiển thị tất cả các kênh cho email đã chọn
            channels_to_display = self.data[self.selected_email_index].get("channels", [])
            if channels_to_display is None: channels_to_display = [] # Đảm bảo là một danh sách

            email_addr = self.data[self.selected_email_index].get('email', 'đã chọn')
            self.status_var.set(f"Đã làm mới xem nhanh cho {len(channels_to_display)} kênh")

        # Cập nhật vùng văn bản xem nhanh với danh sách các kênh đã xác định
        self.update_channel_quick_view(channels_to_display)


    def update_channel_quick_view(self, channels):
        """Điền nội dung vào vùng văn bản Xem nhanh Kênh với chi tiết của các kênh cho trước."""
        self.channel_info_text.config(state=tk.NORMAL) # Tạm thời bật chế độ chỉnh sửa
        self.channel_info_text.delete(1.0, tk.END) # Xóa nội dung hiện tại

        self.current_channels = channels # Lưu danh sách các kênh đang được hiển thị

        # Lấy thông tin cấp email cho tiêu đề xem nhanh
        email_data = {}
        email = "Chưa chọn Email"
        email_note = ""
        recovery_email = "" # Thêm biến email khôi phục
        recovery_phone = "" # Thêm biến sđt khôi phục
        recovery_password = "" # Thêm biến mật khẩu khôi phục
        is_verified = False
        verified_by = ""
        login_location = ""
        is_verification_failed = False


        if self.selected_email_index is not None and (0 <= self.selected_email_index < len(self.data)):
             email_data = self.data[self.selected_email_index]
             email = email_data.get("email", "Không rõ")
             email_note = email_data.get("email_note", "") # Lấy ghi chú email
             recovery_email = email_data.get("recovery_email", "") # Lấy email khôi phục
             recovery_phone = email_data.get("recovery_phone", "") # Lấy sđt khôi phục
             recovery_password = email_data.get("recovery_password", "") # Lấy mật khẩu khôi phục

             is_verified = email_data.get("is_verified", False)
             verified_by = email_data.get("verified_by", "")
             login_location = email_data.get("login_location", "")
             is_verification_failed = email_data.get("verification_failed", False)


        # Chèn tiêu đề Email
        self.channel_info_text.insert(tk.END, f"Email: {email}\n", "title")

        # Chèn thông tin khôi phục nếu có
        recovery_info_str = ""
        if recovery_email: recovery_info_str += f"Email khôi phục: {recovery_email}\n"
        if recovery_password: recovery_info_str += f"Mật khẩu Email khôi phục: {recovery_password}\n" # Bao gồm mật khẩu khôi phục
        if recovery_phone: recovery_info_str += f"SĐT khôi phục: {recovery_phone}\n" # Bao gồm sđt khôi phục

        if recovery_info_str:
             self.channel_info_text.insert(tk.END, f"Thông tin khôi phục:\n", "title")
             self.channel_info_text.insert(tk.END, recovery_info_str, "recovery_info")
             self.channel_info_text.insert(tk.END, "-" * 40 + "\n", "recovery_info") # Dòng phân cách


        # Chèn Ghi chú Email nếu có
        if email_note:
             self.channel_info_text.insert(tk.END, f"Ghi chú Email:\n", "title")
             self.channel_info_text.insert(tk.END, f"{email_note}\n", "note")
             self.channel_info_text.insert(tk.END, "-" * 40 + "\n", "note") # Dòng phân cách

        # Chèn Trạng thái xác minh với tag và ưu tiên phù hợp
        self.channel_info_text.insert(tk.END, f"Trạng thái xác minh: ", "title")
        if is_verification_failed:
             self.channel_info_text.insert(tk.END, "❌ Xác minh thất bại\n", "failed") # Đỏ đậm
        elif is_verified:
            self.channel_info_text.insert(tk.END, "✅ Đã xác minh", "verified") # Xanh dương đậm
            if verified_by: self.channel_info_text.insert(tk.END, f" (Bởi: {verified_by})\n", "verified")
            else: self.channel_info_text.insert(tk.END, "\n", "verified")
        else: # Chưa xác minh và không thất bại
             self.channel_info_text.insert(tk.END, "❌ Chưa xác minh\n", "not_in_use") # Đỏ

        # Chèn Vị trí đăng nhập nếu có
        if login_location: self.channel_info_text.insert(tk.END, f"Vị trí đăng nhập: {login_location}\n", "title")
        # Người xác minh đã được bao gồm nếu trạng thái là Đã xác minh, nhưng thêm độc lập nếu trạng thái là Chưa xác minh nhưng đã ghi nhận Người xác minh
        elif verified_by and not is_verified and not is_verification_failed:
             self.channel_info_text.insert(tk.END, f"Người xác minh (Ghi nhận): {verified_by}\n", "title")


        # Chèn tiêu đề số lượng kênh
        self.channel_info_text.insert(tk.END, f"\nKênh hiển thị: {len(channels)}\n", "title")
        self.channel_info_text.insert(tk.END, "-" * 40 + "\n\n") # Dòng phân cách

        # Chèn chi tiết cho mỗi kênh
        if not channels:
            self.channel_info_text.insert(tk.END, "Hiện tại không hiển thị kênh nào.\n")
        else:
            for i, ch in enumerate(channels):
                name = ch.get("channel_name", "Không tên")
                url = ch.get("channel_url", "")
                in_use = ch.get("in_use", False)
                note = ch.get("note", "")

                self.channel_info_text.insert(tk.END, f"{i+1}. {name}\n", "title") # Số kênh và tên

                if url: self.channel_info_text.insert(tk.END, f"   URL: {url}\n", "url") # URL với kiểu hyperlink

                # Trạng thái (Đang sử dụng) với tag màu
                self.channel_info_text.insert(tk.END, f"   Trạng thái: ", "title")
                self.channel_info_text.insert(tk.END, "✅ Đang sử dụng\n", "in_use") if in_use else self.channel_info_text.insert(tk.END, "❌ Không sử dụng\n", "not_in_use")

                if note: self.channel_info_text.insert(tk.END, f"   Ghi chú: {note}\n", "note") # Ghi chú

                self.channel_info_text.insert(tk.END, "\n") # Khoảng cách giữa các kênh

        self.channel_info_text.config(state=tk.DISABLED) # Tắt chế độ chỉnh sửa sau khi điền nội dung


    def perform_global_search(self, *args):
        """Thực hiện tìm kiếm trên toàn bộ dữ liệu email và kênh dựa trên từ khóa và phạm vi tìm kiếm."""
         # Kiểm tra xem ứng dụng có bị khóa không
        if self._is_locked:
            self.status_var.set("Ứng dụng đang bị khóa. Không thể tìm kiếm.")
            return

        # Tạm thời xóa trace để ngăn chặn vòng lặp vô hạn trong quá trình cập nhật
        self.global_search_var.trace_remove("write", self._search_trace_id)
        self.filter_in_use.trace_remove("write", self._filter_trace_id)

        search_term = self.global_search_var.get().strip().lower()
        scope = self.search_scope.get()
        in_use_only = self.filter_in_use.get()

        # Nếu từ khóa tìm kiếm rỗng và bộ lọc tắt, chuyển về chế độ xem thông thường
        if not search_term and not in_use_only:
            if self.current_view == "search":
                self.current_view = "normal"
                # Đặt lại chỉ báo sắp xếp cho chế độ xem thông thường
                self._email_sort_col = None
                self._email_sort_order = False
                # Làm mới giao diện để hiển thị tất cả dữ liệu ở chế độ xem thông thường
                self.refresh_email_list()
                self.clear_email_details()
                self.clear_channel_details()
                self.channel_tree.delete(*self.channel_tree.get_children())
                self.update_channel_quick_view([])
                self.selected_email_index = None
                self.selected_channel_index = None
                self.status_var.set("Đã xóa tìm kiếm, chế độ xem thông thường đang hoạt động")
            # Thêm lại trace trước khi trả về
            self._search_trace_id = self.global_search_var.trace_add("write", self.perform_global_search)
            self._filter_trace_id = self.filter_in_use.trace_add("write", self.perform_global_search)
            return

        # Nếu chỉ bộ lọc đang bật, cập nhật trạng thái
        if not search_term and in_use_only:
             self.status_var.set("Đang lọc chỉ các kênh 'đang sử dụng'...")
        elif search_term and in_use_only:
             self.status_var.set(f"Đang tìm kiếm '{search_term}' (chỉ các kênh đang sử dụng)...")
        else: # Chỉ có từ khóa tìm kiếm
             self.status_var.set(f"Đang tìm kiếm '{search_term}'...")


        self.current_view = "search" # Đặt chế độ xem là tìm kiếm
        self.search_results = [] # Xóa kết quả tìm kiếm trước đó

        # Xóa dữ liệu treeview và chi tiết hiện tại
        self.email_tree.delete(*self.email_tree.get_children())
        self.channel_tree.delete(*self.channel_tree.get_children())
        self.clear_email_details()
        self.clear_channel_details()
        self.selected_email_index = None
        self.selected_channel_index = None
        self.update_channel_quick_view([])

        # Đặt lại chỉ báo sắp xếp trong hiển thị chế độ tìm kiếm
        self._email_sort_col = None
        self._email_sort_order = False
        for c in ('email', 'channel_count'): self.email_tree.heading(c, text=('Email' if c == 'email' else 'Kênh'))


        found_emails_items = {} # Theo dõi các mục email treeview đã được thêm
        matching_email_count = 0 # Đếm số email có kết quả khớp
        matching_channel_total = 0 # Đếm tổng số kênh khớp


        # Lặp qua tất cả dữ liệu email
        for email_idx, email_data in enumerate(self.data):
            email_addr = email_data.get("email", "").lower()
            email_note = email_data.get("email_note", "").lower() # Thêm trường ghi chú email vào tìm kiếm
            login_loc = email_data.get("login_location", "").lower()
            verified_by_val = email_data.get("verified_by", "").lower() # Lấy trường người xác minh
            # === LẤY TRƯỜNG MỚI CHO TÌM KIẾM ===
            recovery_phone_val = email_data.get("recovery_phone", "").lower()
            # Mật khẩu khôi phục không nên tìm kiếm trực tiếp để bảo mật,
            # nhưng có thể đưa vào phạm vi 'all' hoặc 'emails' nếu cần.
            # Tạm thời chỉ tìm kiếm trong 'all' và 'emails' nếu có.
            recovery_password_val = email_data.get("recovery_password", "").lower() # Lấy mật khẩu khôi phục

            # Kiểm tra xem các trường cấp email có khớp với từ khóa tìm kiếm không
            email_field_matches = False
            if search_term:
                if scope in ("all", "emails") and search_term in email_addr: email_field_matches = True
                if scope in ("all", "emails", "notes") and search_term in email_note: email_field_matches = email_field_matches or True # Tìm kiếm trong ghi chú email
                if scope in ("all", "emails", "location") and search_term in login_loc: email_field_matches = email_field_matches or True
                if scope in ("all", "emails", "verified_by") and search_term in verified_by_val: email_field_matches = email_field_matches or True
                # === THÊM TÌM KIẾM TRONG CÁC TRƯỜNG MỚI ===
                if scope in ("all", "emails", "recovery_phone") and search_term in recovery_phone_val: email_field_matches = email_field_matches or True
                if scope in ("all", "emails") and search_term in recovery_password_val: email_field_matches = email_field_matches or True # Tìm mật khẩu khôi phục chỉ trong all/emails


            channel_matches_filtered = [] # Danh sách để lưu trữ các kênh khớp cho email này
            channels_list = email_data.get("channels", [])
            if channels_list is None: channels_list = [] # Đảm bảo là một danh sách

            # Lặp qua các kênh trong email hiện tại
            for ch_idx, channel in enumerate(channels_list):
                is_in_use = channel.get("in_use", False)

                # Áp dụng bộ lọc 'chỉ đang sử dụng'
                if in_use_only and not is_in_use:
                    continue # Bỏ qua các kênh không đang sử dụng nếu bộ lọc hoạt động

                # Kiểm tra xem các trường kênh có khớp với từ khóa tìm kiếm không
                channel_term_matches = False
                if search_term:
                    ch_name = channel.get("channel_name", "").lower()
                    ch_url = channel.get("channel_url", "").lower()
                    ch_note = channel.get("note", "").lower()

                    if scope == "all" and (search_term in ch_name or search_term in ch_url or search_term in ch_note):
                         channel_term_matches = True
                    elif scope == "names" and search_term in ch_name:
                         channel_term_matches = True
                    elif scope == "urls" and search_term in ch_url:
                         channel_term_matches = True
                    elif scope == "notes" and search_term in ch_note:
                         channel_term_matches = True
                    # Note: Recovery Phone/Password search is only applied at the email level, not per channel.
                else:
                    # Nếu không có từ khóa tìm kiếm, tất cả các kênh đã qua bộ lọc 'đang sử dụng' được coi là khớp
                    channel_term_matches = True


                # Nếu kênh khớp với từ khóa tìm kiếm (hoặc không có từ khóa được chỉ định) VÀ vượt qua bộ lọc...
                if channel_term_matches:
                     # Lưu chỉ mục gốc và dữ liệu kênh
                     channel_matches_filtered.append((ch_idx, channel))

            # Xác định xem tài khoản email này có nên được bao gồm trong kết quả tìm kiếm không
            # Một email được bao gồm nếu nó có trường cấp email khớp HOẶC nó có các kênh khớp (sau khi lọc)
            include_email = email_field_matches or bool(channel_matches_filtered)

            if include_email:
                 matching_email_count += 1
                 matching_channel_total += len(channel_matches_filtered)

                 # Lưu kết quả tìm kiếm cho email này (bao gồm cả kênh nào đã khớp)
                 self.search_results.append({
                     "email_idx": email_idx, # Chỉ mục gốc trong danh sách dữ liệu chính
                     "email_data": email_data, # Tham chiếu đến dữ liệu email thực tế
                     "channel_matches": channel_matches_filtered # Danh sách (chỉ_mục_kênh_gốc, dữ_liệu_kênh)
                 })

                 # Thêm email vào treeview email NẾU nó chưa được thêm
                 # Một email có thể được thêm nhiều lần vào search_results nếu nó có nhiều kết quả khớp,
                 # nhưng chúng ta chỉ muốn nó xuất hiện một lần trong treeview email.
                 if email_idx not in found_emails_items:
                      email_display = email_data.get("email", "Không có Email")
                      channel_count_display = len(channels_list) # Hiển thị tổng số kênh trong dữ liệu gốc

                      # Xác định tag cho mục treeview email dựa trên ưu tiên (Thất bại > Đã xác minh > Đang sử dụng)
                      tags = []
                      is_verification_failed = email_data.get("verification_failed", False)
                      is_verified = email_data.get("is_verified", False)
                      # Kiểm tra xem *bất kỳ* kênh nào trong danh sách gốc có đang sử dụng không
                      has_in_use = any(ch.get("in_use", False) for ch in channels_list) if channels_list else False

                      if is_verification_failed: tags.append('verification_failed_tag') # Ưu tiên cao nhất (Đỏ đậm)
                      elif is_verified: tags.append('verified_tag') # Ưu tiên thứ hai (Xanh dương đậm)
                      elif has_in_use: tags.append('in_use_tag') # Ưu tiên thứ ba (Xanh lá)
                      # Không có tag nào được áp dụng nếu không đáp ứng điều kiện nào ở trên

                      # Chèn mục email vào treeview
                      item_id = self.email_tree.insert("", tk.END, values=(email_display, channel_count_display))
                      # Ánh xạ chỉ mục email gốc với ID mục treeview
                      found_emails_items[email_idx] = item_id

                      # Áp dụng tag nếu có
                      if tags: self.email_tree.item(item_id, tags=tuple(tags))


        # Cập nhật thanh trạng thái với tóm tắt tìm kiếm
        self.status_var.set(f"Tìm kiếm: {matching_email_count} tài khoản, {matching_channel_total} kênh khớp với tiêu chí.")

        # Nếu không có email nào khớp, xóa chi tiết và xem nhanh
        if matching_email_count == 0:
             self.clear_email_details()
             self.update_channel_quick_view([]) # Đảm bảo xem nhanh trống


        # Thêm lại trace sau khi cập nhật hoàn tất
        self._search_trace_id = self.global_search_var.trace_add("write", self.perform_global_search)
        self._filter_trace_id = self.filter_in_use.trace_add("write", self.perform_global_search)


    def on_email_select(self, event):
        """Xử lý khi chọn một email trong treeview email."""
         # Kiểm tra xem ứng dụng có bị khóa không
        if self._is_locked:
            self.email_tree.selection_remove(self.email_tree.selection()) # Bỏ chọn nếu click khi bị khóa
            return # Không xử lý sự kiện chọn khi bị khóa

        selected_items = self.email_tree.selection()

        # Dừng luồng tạo OTP đang chạy khi lựa chọn thay đổi
        self.otp_thread_id = None

        if not selected_items:
            # Nếu bỏ chọn, đặt lại mọi thứ
            self.selected_email_index = None
            self.selected_channel_index = None
            self.clear_email_details()
            self.clear_channel_details()
            self.channel_tree.delete(*self.channel_tree.get_children()) # Xóa treeview kênh
            self.update_channel_quick_view([]) # Xóa xem nhanh
            self.status_var.set("Đã bỏ chọn email")
            # Đặt lại chỉ báo sắp xếp danh sách kênh trực quan
            self._channel_sort_col = None; self._channel_sort_order = False
            for c in ('status', 'name', 'url', 'note'): self.channel_tree.heading(c, text=c.replace('_', ' ').title())
            return

        selected_item = selected_items[0] # Lấy ID của mục được chọn
        tree_idx = self.email_tree.index(selected_item) # Lấy chỉ mục của mục được chọn trong treeview

        email_data = None
        channels_to_display = [] # Danh sách các kênh sẽ hiển thị trong treeview kênh và xem nhanh

        # Xác định dữ liệu email thực tế và các kênh dựa trên chế độ xem hiện tại (thông thường hoặc tìm kiếm)
        if self.current_view == "search":
            # Ở chế độ tìm kiếm, chỉ mục treeview ánh xạ tới danh sách search_results
            if 0 <= tree_idx < len(self.search_results):
                search_result = self.search_results[tree_idx]
                # Lấy chỉ mục email gốc và dữ liệu từ kết quả tìm kiếm
                self.selected_email_index = search_result["email_idx"]
                email_data = self.data[self.selected_email_index]
                # Lấy các kênh khớp với tiêu chí tìm kiếm cho email này
                channels_to_display = [ch for _, ch in search_result["channel_matches"]]

                email_addr = email_data.get('email', 'đã chọn')
                self.status_var.set(f"Tìm kiếm: {len(channels_to_display)} kết quả khớp cho {email_addr}")
            else:
                # Đáng lẽ không xảy ra nếu treeview được điền đúng từ search_results
                self.selected_email_index = None
                self.status_var.set("Lỗi chọn kết quả tìm kiếm")
                return

        else: # Chế độ xem thông thường
            # Ở chế độ xem thông thường, chỉ mục treeview ánh xạ trực tiếp tới chỉ mục trong danh sách data
            if 0 <= tree_idx < len(self.data):
                self.selected_email_index = tree_idx
                email_data = self.data[tree_idx]
                # Lấy tất cả các kênh cho email này ở chế độ xem thông thường
                channels_to_display = email_data.get("channels", [])
                if channels_to_display is None: channels_to_display = [] # Đảm bảo là một danh sách

                email_addr = self.data[self.selected_email_index].get('email', 'đã chọn')
                self.status_var.set(f"{len(channels_to_display)} kênh cho {email_addr}")
            else:
                # Đáng lẽ không xảy ra nếu treeview được điền đúng từ self.data
                self.selected_email_index = None
                self.status_var.set("Lỗi chọn thông thường")
                return

        # Điền nội dung vào các thành phần giao diện nếu dữ liệu email được tìm thấy thành công
        if email_data:
            self.populate_email_details(email_data) # Điền nội dung vào biểu mẫu chi tiết email

            # Clear và repopulate treeview kênh
            self.channel_tree.delete(*self.channel_tree.get_children())
            self.current_channels = channels_to_display # Đặt danh sách kênh hiện tại cho treeview và xem nhanh

            # Đặt lại chỉ báo sắp xếp danh sách kênh trực quan trước khi điền nội dung
            self._channel_sort_col = None; self._channel_sort_order = False
            for c in ('status', 'name', 'url', 'note'): self.channel_tree.heading(c, text=c.replace('_', ' ').title())

            # Chèn các kênh vào treeview kênh
            for ch in channels_to_display:
                status = "✅" if ch.get("in_use", False) else "❌"
                self.channel_tree.insert("", tk.END, values=(status, ch.get("channel_name", ""), ch.get("channel_url", ""), ch.get("note", "")))

            # Cập nhật bảng xem nhanh với các kênh của email đã chọn
            self.update_channel_quick_view(channels_to_display)

            # Xóa biểu mẫu chi tiết kênh và đặt lại chỉ mục kênh đã chọn
            self.selected_channel_index = None
            self.clear_channel_details()

        else:
             # Xóa phòng thủ nếu email_data không được tải vì lý do nào đó dù đã chọn
             self.selected_email_index = None
             self.selected_channel_index = None
             self.clear_email_details()
             self.clear_channel_details()
             self.channel_tree.delete(*self.channel_tree.get_children())
             self.update_channel_quick_view([])
             self.status_var.set("Không thể tải chi tiết email")


    def populate_email_details(self, email_data):
        """Điền nội dung vào biểu mẫu chi tiết email bằng dữ liệu từ một từ điển email cho trước."""
        # Đặt lại hiển thị mật khẩu và trường nhập liệu
        self.show_password.set(False)
        self.password_entry.config(show="*")
        # === ÁP DỤNG CHO CẢ TRƯỜNG MẬT KHẨU KHÔI PHỤC ===
        self.recovery_password_entry.config(show="*")

        # Reset styles cho các trường nhập liệu
        self.email_entry.config(style='TEntry')
        self.recovery_email_entry.config(style='TEntry') # Cập nhật tên entry
        self.key_entry.config(style='TEntry')
        self.password_entry.config(style='TEntry')
        # === RESET STYLE CHO TRƯỜNG MỚI ===
        self.recovery_password_entry.config(style='TEntry')
        self.recovery_phone_entry.config(style='TEntry')


        # Xóa nội dung tất cả các trường nhập liệu
        self.email_entry.delete(0, tk.END)
        self.password_entry.delete(0, tk.END)
        self.recovery_email_entry.delete(0, tk.END) # Cập nhật tên entry
        # === XÓA TRƯỜNG MỚI ===
        self.recovery_password_entry.delete(0, tk.END)
        self.recovery_phone_entry.delete(0, tk.END)

        self.key_entry.delete(0, tk.END)
        # Xóa nội dung trường Ghi chú Email (tk.Text)
        self.email_note_text.config(state=tk.NORMAL) # Bật để xóa
        self.email_note_text.delete(1.0, tk.END)

        # Đặt lại biến checkbox và chuỗi về giá trị mặc định (False/rỗng)
        self.is_verified_var.set(False)
        self.verified_by_var.set("")
        self.login_location_var.set("")
        self.verification_failed_var.set(False)

        # Xóa xem trước và biến mã QR
        self.clear_qrcode_image_variable()

        # Chèn dữ liệu từ từ điển vào các trường
        self.email_entry.insert(0, email_data.get("email", ""))
        self.password_entry.insert(0, email_data.get("password", ""))
        self.recovery_email_entry.insert(0, email_data.get("recovery_email", "")) # Cập nhật tên entry
        # === CHÈN DỮ LIỆU CHO TRƯỜNG MỚI ===
        self.recovery_password_entry.insert(0, email_data.get("recovery_password", ""))
        self.recovery_phone_entry.insert(0, email_data.get("recovery_phone", ""))

        self.key_entry.insert(0, email_data.get("2fa_key", ""))
        self.email_note_text.insert(tk.END, email_data.get("email_note", "")) # Chèn ghi chú email
        self.is_verified_var.set(email_data.get("is_verified", False))
        self.verified_by_var.set(email_data.get("verified_by", ""))
        self.login_location_var.set(email_data.get("login_location", ""))
        self.verification_failed_var.set(email_data.get("verification_failed", False)) # Đặt trạng thái checkbox mới

        self.email_note_text.config(state=tk.NORMAL) # Luôn cho phép chỉnh sửa ghi chú


        # Tải và hiển thị xem trước ảnh mã QR
        decrypted_b64_img = email_data.get("qrcode_image_base64", "")
        self.qrcode_image_base64_decrypted_var.set(decrypted_b64_img)
        self.display_qrcode_image_preview(decrypted_b64_img)

        # Bắt đầu trình tạo OTP nếu có khóa 2FA
        self.start_otp(email_data.get("2fa_key", ""))

        # Chuyển sang tab Chi tiết Email
        self.notebook.select(0)

        # Đặt lại cờ dữ liệu đã thay đổi khi tải dữ liệu hiện có vào biểu mẫu
        self._data_changed = False


    def clear_email_details(self):
         """Xóa nội dung tất cả các trường trong biểu mẫu chi tiết email và các thành phần liên quan."""
         # Reset styles cho các trường nhập liệu
         self.email_entry.config(style='TEntry')
         self.recovery_email_entry.config(style='TEntry') # Cập nhật tên entry
         self.key_entry.config(style='TEntry')
         self.password_entry.config(style='TEntry') # Password entry as well
         # === RESET STYLE CHO TRƯỜNG MỚI ===
         self.recovery_password_entry.config(style='TEntry')
         self.recovery_phone_entry.config(style='TEntry')


         self.email_entry.delete(0, tk.END)
         self.password_entry.delete(0, tk.END)
         self.recovery_email_entry.delete(0, tk.END) # Cập nhật tên entry
         # === XÓA TRƯỜNG MỚI ===
         self.recovery_password_entry.delete(0, tk.END)
         self.recovery_phone_entry.delete(0, tk.END)
         self.key_entry.delete(0, tk.END)

         # Xóa nội dung trường Ghi chú Email (tk.Text)
         self.email_note_text.config(state=tk.NORMAL) # Bật để xóa
         self.email_note_text.delete(1.0, tk.END)


         # Đặt lại biến checkbox và chuỗi về mặc định (False/rỗng)
         self.is_verified_var.set(False)
         self.verified_by_var.set("")
         self.login_location_var.set("")
         self.verification_failed_var.set(False) # Xóa trạng thái checkbox mới

         # Đặt lại chức năng bật/tắt hiển thị mật khẩu
         self.show_password.set(False)
         self.password_entry.config(show="*")
         # === ÁP DỤNG CHO CẢ TRƯỜNG MẬT KHẨU KHÔI PHỤC ===
         self.recovery_password_entry.config(show="*")


         # Dừng tạo OTP và đặt lại hiển thị
         self.otp_thread_id = None # Ra hiệu luồng OTP dừng lại
         self.otp_label.config(text="------", foreground="gray")
         # self.otp_time_label.config(text="Không có Khóa 2FA") # Xóa widget này
         # === XÓA TEXT ITEM TRÊN CANVAS ===
         if hasattr(self, 'otp_timer_text_item'):
             self.otp_canvas.itemconfig(self.otp_timer_text_item, text="")
         # Đặt lại vòng cung canvas OTP
         if hasattr(self, 'otp_arc'):
             self.otp_canvas.itemconfig(self.otp_arc, extent=0, outline='#bdc3c7')

         # Xóa xem trước và biến mã QR
         self.clear_qrcode_image_variable()

         # Đặt lại cờ dữ liệu đã thay đổi khi xóa
         self._data_changed = False


    def clear_search(self):
        """Xóa nội dung trường nhập tìm kiếm toàn cục và bộ lọc, trở về chế độ xem thông thường."""
        self.global_search_var.set("") # Xóa biến sẽ kích hoạt perform_global_search
        self.filter_in_use.set(False) # Xóa biến cũng sẽ kích hoạt perform_global_search
        # Hàm perform_global_search xử lý việc chuyển về chế độ "normal" khi search_term và filter rỗng/False


    def refresh_email_list(self):
        """Làm mới hiển thị treeview email dựa trên danh sách self.data hiện tại."""
        # Chỉ làm mới danh sách email ở chế độ xem thông thường hoặc khi bị khóa.
        # Chế độ tìm kiếm được xử lý bởi perform_global_search.
        # Nếu bị khóa, chỉ hiển thị danh sách trống hoặc cũ, không tương tác
        if self.current_view != "normal" and not self._is_locked:
             return

        # Xóa các mục hiện tại trong treeview
        self.email_tree.delete(*self.email_tree.get_children())

        # Làm mới chỉ báo sắp xếp trên tiêu đề nếu có cột sắp xếp được đặt
        if self._email_sort_col:
             for c in ('email', 'channel_count'):
                heading_text = 'Email' if c == 'email' else 'Kênh'
                current_text = self.email_tree.heading(c, 'text')
                clean_text = current_text.replace(' ▲', '').replace(' ▼', '') # Xóa các mũi tên hiện có

                if c == self._email_sort_col:
                    arrow = ' ▼' if self._email_sort_order else ' ▲' # Thêm mũi tên cho cột sắp xếp hiện tại
                    self.email_tree.heading(c, text=f"{clean_text}{arrow}")
                else:
                    self.email_tree.heading(c, text=clean_text) # Đảm bảo các cột khác không có mũi tên

        # Nếu ứng dụng bị khóa, không điền lại Treeview bằng dữ liệu nhạy cảm
        if self._is_locked:
             self.email_tree.insert("", tk.END, values=("Ứng dụng đang bị khóa...", ""))
             return # Dừng ở đây

        # Điền lại treeview từ danh sách self.data có thể đã được sắp xếp
        for idx, email_data in enumerate(self.data):
            email_address = email_data.get("email", "")
            channels_list = email_data.get("channels", [])
            channel_count = len(channels_list) if channels_list is not None else 0

            # Xác định tag cho kiểu dáng trực quan dựa trên ưu tiên (Thất bại > Đã xác minh > Đang sử dụng)
            tags = []
            is_verification_failed = email_data.get("verification_failed", False)
            is_verified = email_data.get("is_verified", False)
            # Kiểm tra xem *bất kỳ* kênh nào trong danh sách gốc có đang sử dụng không
            has_in_use = any(ch.get("in_use", False) for ch in channels_list) if channels_list else False

            if is_verification_failed:
                tags.append('verification_failed_tag') # Ưu tiên cao nhất (Đỏ đậm)
            elif is_verified:
                tags.append('verified_tag') # Ưu tiên thứ hai (Xanh dương đậm)
            elif has_in_use:
                tags.append('in_use_tag') # Ưu tiên thứ ba (Xanh lá)
            # Không có tag nào được áp dụng nếu không đáp ứng điều kiện nào ở trên

            # Chèn mục email vào treeview
            item_id = self.email_tree.insert("", tk.END, values=(email_address, channel_count))

            # Áp dụng các tag đã xác định cho mục treeview
            if tags:
                 self.email_tree.item(item_id, tags=tuple(tags))


    def clear_channel_details(self):
        """Xóa nội dung tất cả các trường trong biểu mẫu chi tiết kênh."""
        # Reset styles cho các trường nhập liệu
        self.url_entry.config(style='TEntry')
        self.name_entry.config(style='TEntry') # Tên kênh cũng có thể cần xác thực sau này
        self.note_entry.config(style='TEntry') # Ghi chú kênh cũng có thể cần xác thực sau này

        self.url_entry.delete(0, tk.END)
        self.name_entry.delete(0, tk.END)
        self.note_entry.delete(0, tk.END)
        self.use_var.set(False) # Bỏ chọn checkbox 'Đang sử dụng'
        self.selected_channel_index = None # Đặt lại chỉ mục kênh đã chọn
        self._data_changed = False # Đặt lại cờ dữ liệu đã thay đổi khi xóa

    def update_channel_list(self, *args):
        """Làm mới hiển thị treeview kênh cho email hiện đang chọn."""
        # Chỉ cập nhật danh sách kênh ở chế độ xem thông thường. Chế độ tìm kiếm được xử lý bởi on_email_select trong chế độ tìm kiếm.
        # Không cập nhật nếu bị khóa
        if self.current_view == "search" or self._is_locked:
             return

        # Xóa các mục hiện tại trong treeview kênh
        self.channel_tree.delete(*self.channel_tree.get_children())
        self.current_channels = [] # Xóa danh sách các kênh hiện đang được hiển thị

        # Kiểm tra xem có email nào được chọn không
        if self.selected_email_index is None or not (0 <= self.selected_email_index < len(self.data)):
            self.status_var.set("Chưa chọn email"); self.update_channel_quick_view([]); return # Xóa xem nhanh
            return # Thoát nếu không có email nào được chọn

        # Lấy danh sách kênh cho email đã chọn
        channels = self.data[self.selected_email_index].get("channels", [])
        if channels is None: channels = [] # Đảm bảo là một danh sách

        self.current_channels = channels # Đặt danh sách các kênh đang được hiển thị

        # Nếu có cột sắp xếp được đặt, để phương thức sắp xếp điền lại treeview
        if self._channel_sort_col:
             self._sort_channel_tree(self._channel_sort_col)
             return # Phương thức sắp xếp sẽ gọi lại update_channel_list để điền nội dung

        # Nếu không áp dụng sắp xếp nào, điền nội dung treeview theo thứ tự hiện tại
        for ch in channels:
            status = "✅" if ch.get("in_use", False) else "❌"
            self.channel_tree.insert("", tk.END, values=(status, ch.get("channel_name", ""), ch.get("channel_url", ""), ch.get("note", "")))

        # Cập nhật thanh trạng thái và xem nhanh
        email_addr = self.data[self.selected_email_index].get('email', 'đã chọn')
        self.status_var.set(f"{len(channels)} kênh cho {email_addr}")
        self.update_channel_quick_view(channels)


    def on_channel_select(self, event):
        """Xử lý khi chọn một kênh trong treeview kênh."""
         # Kiểm tra xem ứng dụng có bị khóa không
        if self._is_locked:
            self.channel_tree.selection_remove(self.channel_tree.selection()) # Bỏ chọn nếu click khi bị khóa
            return # Không xử lý sự kiện chọn khi bị khóa


        selected_items = self.channel_tree.selection()

        if not selected_items:
            # Nếu bỏ chọn, xóa biểu mẫu chi tiết kênh
            self.clear_channel_details()
            return

        selected_item = selected_items[0] # Lấy ID của mục được chọn
        tree_idx = self.channel_tree.index(selected_item) # Lấy chỉ mục của mục được chọn trong treeview

        channel_data = None
        original_idx = None # Đây sẽ lưu trữ chỉ mục của kênh trong danh sách kênh GỐC của email (cần cho việc lưu/xóa)

        # Đảm bảo email được chọn trước khi cố gắng tìm dữ liệu kênh
        if self.selected_email_index is None or not (0 <= self.selected_email_index < len(self.data)):
             # Trường hợp này đáng lẽ phải được ngăn chặn bởi on_email_select xóa treeview kênh, nhưng kiểm tra để đảm bảo.
             self.clear_channel_details()
             self.selected_channel_index = None
             self.status_var.set("Lỗi: Vui lòng chọn email trước.")
             return

        # Lấy danh sách kênh liên quan đến chế độ xem hiện tại (tất cả kênh cho email ở chế độ thông thường, các kênh đã lọc ở chế độ tìm kiếm)
        # Lưu ý: self.current_channels chứa danh sách các kênh hiện đang được hiển thị trong treeview
        channels_list_in_view = self.current_channels

        if self.current_view == "search":
             # Ở chế độ tìm kiếm, chỉ mục treeview ánh xạ tới một mục trong danh sách search_result["channel_matches"] trong kết quả tìm kiếm cho email đã chọn
             search_result = next((sr for sr in self.search_results if sr["email_idx"] == self.selected_email_index), None)

             if search_result and 0 <= tree_idx < len(search_result["channel_matches"]):
                  # Lấy chỉ mục gốc và dữ liệu của kênh từ kết quả tìm kiếm kênh khớp
                  index_in_data, data_to_delete = search_result["channel_matches"][tree_idx]
                  self.selected_channel_index = index_in_data # Lưu chỉ mục gốc để lưu/xóa

             else:
                  # Đáng lẽ không xảy ra nếu treeview được điền đúng từ search_result["channel_matches"]
                  self.clear_channel_details()
                  self.selected_channel_index = None
                  self.status_var.set("Lỗi chọn kênh tìm kiếm")
                  return

        else: # Chế độ xem thông thường
             # Ở chế độ xem thông thường, chỉ mục treeview ánh xạ trực tiếp tới chỉ mục trong danh sách kênh của email (có thể đã sắp xếp)
             index_in_view = tree_idx # Chỉ mục trong danh sách hiện đang hiển thị/đã sắp xếp

             channels_list_full = self.data[self.selected_email_index].get("channels", [])
             if channels_list_full is None: channels_list_full = []

             if 0 <= index_in_view < len(channels_list_in_view):
                 # Lấy dữ liệu kênh từ danh sách hiện đang hiển thị
                 channel_data = channels_list_in_view[index_in_view]
                 # We need to find the index of this specific channel_data item in the *original* full list for saving/deletion.
                 # Finding the original index is more robust if the list is sorted.
                 try:
                     # Find the index of the current channel_data dict within the original full list (by reference)
                     original_idx_in_full_list = next(i for i, ch in enumerate(channels_list_full) if ch is channel_data)
                     self.selected_channel_index = original_idx_in_full_list # Store the original index
                 except StopIteration:
                     # Should not happen if data consistency is maintained
                     messagebox.showerror("Lỗi Nội bộ", "Không tìm thấy kênh trong danh sách dữ liệu gốc.", parent=self.root)
                     self.clear_channel_details()
                     self.selected_channel_index = None
                     return
             else:
                  # Should not happen if treeview is populated correctly
                  self.clear_channel_details()
                  self.selected_channel_index = None
                  self.status_var.set("Lỗi chọn kênh thông thường")
                  return


        # Fill the channel details form if channel data was successfully found
        if channel_data:
            # Reset styles for channel entry fields
            self.url_entry.config(style='TEntry')
            self.name_entry.config(style='TEntry')
            self.note_entry.config(style='TEntry')

            self.url_entry.delete(0, tk.END)
            self.name_entry.delete(0, tk.END)
            self.note_entry.delete(0, tk.END)

            self.url_entry.insert(0, channel_data.get("channel_url", ""))
            self.name_entry.insert(0, channel_data.get("channel_name", ""))
            self.note_entry.insert(0, channel_data.get("note", ""))
            self.use_var.set(channel_data.get("in_use", False))

            # Switch to the Channel Management tab
            self.notebook.select(1)

            self.status_var.set(f"Kênh '{channel_data.get('channel_name', 'Không tên')}' đã được chọn")
            self._data_changed = False # Reset data changed flag


        else:
             # Defensive clear if channel_data wasn't loaded for some reason
             self.clear_channel_details()
             self.selected_channel_index = None
             self.status_var.set("Không thể tải chi tiết kênh")


    # --- Phương thức OTP ---
    def start_otp(self, key):
        """Bắt đầu luồng trình tạo OTP nếu khóa hợp lệ được cung cấp."""
        # Gán một ID duy nhất mới cho luồng sắp khởi chạy.
        # Điều này cho phép chúng ta ra hiệu cho luồng *trước đó* dừng lại nếu ID của nó không khớp.
        self.otp_thread_id = time.time()

        key = key.strip().replace(" ", "").upper() # Làm sạch khóa

        if not key:
            # Nếu không có khóa, dừng bất kỳ luồng nào đang chạy và đặt lại hiển thị
            self.otp_thread_id = None
            self.otp_label.config(text="------", foreground="gray")
            # self.otp_time_label.config(text="Không có Khóa 2FA") # Loại bỏ widget này
            # === RESET TEXT ITEM TRÊN CANVAS ===
            if hasattr(self, 'otp_timer_text_item'):
                 self.otp_canvas.itemconfig(self.otp_timer_text_item, text="")
            if hasattr(self, 'otp_arc'):
                self.otp_canvas.itemconfig(self.otp_arc, extent=0, outline='#bdc3c7')
            return

        # Xác thực khóa đã làm sạch
        if not self.validate_2fa_key(key):
            # Nếu khóa không hợp lệ, dừng luồng và hiển thị lỗi
            self.otp_thread_id = None
            self.otp_label.config(text="Khóa không hợp lệ", foreground="#e74c3c")
            # self.otp_time_label.config(text="Lỗi") # Loại bỏ widget này
            # === RESET TEXT ITEM TRÊN CANVAS ===
            if hasattr(self, 'otp_timer_text_item'):
                 self.otp_canvas.itemconfig(self.otp_timer_text_item, text="")
            if hasattr(self, 'otp_arc'):
                self.otp_canvas.itemconfig(self.otp_arc, extent=0, outline='#bdc3c7')
            self.status_var.set("Lỗi: Định dạng Khóa 2FA không hợp lệ.")
            # Đặt style lỗi cho key_entry
            self.key_entry.config(style='Error.TEntry')
            return

        # Đảm bảo style key_entry bình thường nếu khóa hợp lệ
        self.key_entry.config(style='TEntry')

        # Bắt đầu vòng lặp tạo OTP trong một luồng riêng
        # Truyền thread_id vừa tạo để vòng lặp biết liệu nó có nên tiếp tục hay không
        # Đảm bảo luồng chỉ chạy nếu ứng dụng không bị khóa
        if not self._is_locked:
             threading.Thread(target=self.otp_loop, args=(key, self.otp_thread_id), daemon=True).start()


    def otp_loop(self, key, thread_id):
        """Tạo và cập nhật hiển thị OTP trong một vòng lặp."""
        # Vòng lặp chỉ tiếp tục nếu thread_id hiện tại khớp với otp_thread_id hiện tại của ứng dụng
        # và cửa sổ root vẫn tồn tại VÀ ứng dụng không bị khóa.
        while self.otp_thread_id == thread_id and self.root and self.root.winfo_exists() and not self._is_locked:
            try:
                totp = pyotp.TOTP(key)
                code = totp.now() # Lấy mã OTP hiện tại
                # Tính thời gian còn lại cho đến OTP tiếp theo
                left = 30 - int(time.time()) % 30 # Epoch TOTP là 30 giây

                # Update UI elements on the main thread using root.after()
                if self.root.winfo_exists(): # Double-check root exists before calling after()
                     # Update OTP code label
                     self.root.after(0, lambda c=code: self.otp_label.config(text=c, foreground="#27ae60"))

                     # === CẬP NHẬT TEXT ITEM TRÊN CANVAS VÀ MÀU SẮC ===
                     if hasattr(self, 'otp_timer_text_item') and hasattr(self, 'otp_arc'):
                         # Update canvas timer text
                         self.root.after(0, lambda l=left: self.otp_canvas.itemconfig(self.otp_timer_text_item, text=str(l)))

                         # Calculate progress and color for the arc
                         extent = 360 * left / 30 # Angle of the arc based on time remaining
                         # Change color based on time remaining
                         color = "#2ecc71" if left >= 20 else ("#f39c12" if left >= 10 else "#e74c3c") # Green, Orange, Red
                         self.root.after(0, lambda e=extent: self.otp_canvas.itemconfig(self.otp_arc, extent=e))
                         self.root.after(0, lambda clr=color: self.otp_canvas.itemconfig(self.otp_arc, outline=clr))
                         # Match canvas text color to arc color
                         self.root.after(0, lambda clr=color: self.otp_canvas.itemconfig(self.otp_timer_text_item, fill=clr))


            except Exception as e:
                # Handle any errors during OTP generation or UI update
                print(f"Lỗi luồng OTP: {e}")
                if self.root.winfo_exists():
                     self.root.after(0, lambda: self.otp_label.config(text="Lỗi", foreground="#e74c3c"))
                     # self.root.after(0, lambda: self.otp_time_label.config(text="Lỗi khóa")) # Loại bỏ widget này
                     # === RESET TEXT ITEM TRÊN CANVAS VÀ VÒNG CUNG ===
                     if hasattr(self, 'otp_timer_text_item'):
                         self.root.after(0, lambda: self.otp_canvas.itemconfig(self.otp_timer_text_item, text="")) # Clear text
                     if hasattr(self, 'otp_arc'):
                         self.root.after(0, lambda: self.otp_canvas.itemconfig(self.otp_arc, extent=0, outline='#bdc3c7')) # Reset arc

                     self.root.after(0, lambda err=e: self.status_var.set(f"Lỗi luồng OTP: {err}"))
                # Stop the thread on error
                self.otp_thread_id = None
                break # Exit the while loop

            # Wait for 1 second before the next update
            if self.root.winfo_exists() and not self._is_locked: # Chỉ sleep nếu root còn tồn tại và không bị khóa
                time.sleep(1)
            else:
                # Exit loop immediately if root window is destroyed or locked
                break


    # --- Phương thức Xác thực ---
    def validate_email(self, email):
        """Xác thực xem chuỗi nhập có phải là một địa chỉ email hợp lệ không."""
        email_regex = r'^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$'
        return re.match(email_regex, email) is not None

    def validate_url(self, url):
        """Xác thực xem chuỗi nhập có phải là một URL hợp lệ không."""
        # Regex này cơ bản và có thể cần tinh chỉnh để xác thực URL nghiêm ngặt hơn
        url_regex = r'^https?://[^\s/$.?#].[^\s]*$'
        return re.match(url_regex, url) is not None

    def validate_2fa_key(self, key):
        """Xác thực xem chuỗi nhập có phải là một khóa 2FA Base32 hợp lệ không."""
        key = key.strip().replace(" ", "").upper() # Làm sạch khóa (xóa khoảng trắng, chuyển hoa)
        if not key: return True # Khóa rỗng được coi là hợp lệ (không có 2FA)
        try:
            # Hàm pyotp.TOTP constructor tự động xác thực định dạng khóa (Base32)
            # Nó sẽ đưa ra ValueError nếu khóa không hợp lệ Base32
            pyotp.TOTP(key)
            return True
        except ValueError:
            # Nếu pyotp đưa ra ValueError, định dạng khóa không hợp lệ Base32
            return False
        except Exception:
            # Bắt các lỗi khác có thể xảy ra
            return False


    # --- Thao tác CRUD ---
    def save_email(self):
        """Lưu chi tiết email hiện tại từ biểu mẫu vào danh sách dữ liệu."""
         # Kiểm tra xem ứng dụng có bị khóa không
        if self._is_locked:
            self.status_var.set("Ứng dụng đang bị khóa. Không thể lưu.")
            return

        # Kiểm tra xem email hợp lệ có được chọn không hoặc chúng ta đang thêm một email mới
        if self.selected_email_index is not None and not (0 <= self.selected_email_index < len(self.data)):
             messagebox.showwarning("Lỗi", "Chỉ mục email được chọn không hợp lệ.", parent=self.root)
             return

        # Lấy dữ liệu từ các trường biểu mẫu
        email = self.email_entry.get().strip()
        pwd = self.password_entry.get().strip()
        recovery_email = self.recovery_email_entry.get().strip() # Cập nhật tên entry
        # === LẤY DỮ LIỆU TỪ TRƯỜNG MỚI ===
        recovery_password = self.recovery_password_entry.get().strip()
        recovery_phone = self.recovery_phone_entry.get().strip()

        key = self.key_entry.get().strip().replace(" ", "").upper() # Làm sạch khóa 2FA
        email_note = self.email_note_text.get(1.0, tk.END).strip() # Lấy nội dung ghi chú email
        is_verified = self.is_verified_var.get()
        verified_by = self.verified_by_var.get().strip()
        login_location = self.login_location_var.get().strip()
        verification_failed = self.verification_failed_var.get() # Lấy giá trị checkbox mới
        decrypted_b64_img = self.qrcode_image_base64_decrypted_var.get() # Lấy dữ liệu ảnh base64

        # Reset styles lỗi trước khi xác thực lại
        self.email_entry.config(style='TEntry')
        self.recovery_email_entry.config(style='TEntry') # Cập nhật tên entry
        self.key_entry.config(style='TEntry')
        self.password_entry.config(style='TEntry')
        # === RESET STYLE CHO TRƯỜNG MỚI ===
        self.recovery_password_entry.config(style='TEntry')
        self.recovery_phone_entry.config(style='TEntry')


        # Thực hiện xác thực cơ bản
        if not email:
            messagebox.showwarning("Thiếu thông tin", "Địa chỉ email là bắt buộc.", parent=self.root)
            self.email_entry.config(style='Error.TEntry')
            self.email_entry.focus_set()
            return
        if not self.validate_email(email):
            messagebox.showwarning("Xác thực", "Định dạng địa chỉ email không hợp lệ.", parent=self.root)
            self.email_entry.config(style='Error.TEntry')
            self.email_entry.focus_set()
            return
        if recovery_email and not self.validate_email(recovery_email): # Xác thực email khôi phục
             messagebox.showwarning("Xác thực", "Định dạng địa chỉ email khôi phục không hợp lệ.", parent=self.root)
             self.recovery_email_entry.config(style='Error.TEntry')
             self.recovery_email_entry.focus_set()
             return
        if key and not self.validate_2fa_key(key):
            messagebox.showwarning("Xác thực", "Định dạng Khóa 2FA không hợp lệ.", parent=self.root)
            self.key_entry.config(style='Error.TEntry')
            self.key_entry.focus_set()
            return
        # === THÊM XÁC THỰC ĐƠN GIẢN CHO SỐ ĐIỆN THOẠI (TÙY CHỌN) ===
        # Có thể thêm regex phức tạp hơn cho số điện thoại nếu cần
        if recovery_phone and not re.match(r'^\+?[0-9\s\-\(\)]+$', recovery_phone):
            messagebox.showwarning("Xác thực", "Định dạng số điện thoại khôi phục không hợp lệ.", parent=self.root)
            self.recovery_phone_entry.config(style='Error.TEntry')
            self.recovery_phone_entry.focus_set()
            return


        # Kiểm tra trùng lặp địa chỉ email (không phân biệt chữ hoa chữ thường)
        current_idx = self.selected_email_index if self.selected_email_index is not None else -1 # -1 có nghĩa là thêm mới
        duplicate_idx = next((i for i, item in enumerate(self.data)
                              if i != current_idx and item.get("email", "").lower() == email.lower()), None)

        if duplicate_idx is not None:
            if not messagebox.askyesno("Trùng lặp", f"Địa chỉ email '{email}' đã tồn tại. Bạn có muốn lưu mục mới/cập nhật này không?", parent=self.root):
                 return # Người dùng chọn không lưu nếu trùng lặp


        # Chuẩn bị từ điển dữ liệu email
        email_item_data = {
            "email": email,
            "password": pwd,
            "recovery_email": recovery_email, # Cập nhật tên khóa
            # === BAO GỒM TRƯỜNG MỚI ===
            "recovery_password": recovery_password,
            "recovery_phone": recovery_phone,

            "2fa_key": key,
            "email_note": email_note, # Bao gồm trường ghi chú email
            "is_verified": is_verified,
            "verified_by": verified_by,
            "login_location": login_location,
            "verification_failed": verification_failed, # Bao gồm trường mới
            "qrcode_image_base64": decrypted_b64_img,
            "channels": [] # Đặt chỗ, sẽ thêm kênh hiện có nếu cập nhật
        }

        message = "đã cập nhật" # Thông báo mặc định
        if self.selected_email_index is not None:
            # If updating email, keep its current channels list
            channels_data = self.data[self.selected_email_index].get("channels", [])
            email_item_data["channels"] = channels_data if channels_data is not None else []
            # Replace the existing item in the data list
            self.data[self.selected_email_index] = email_item_data
        else:
            # If adding a new email, append it to the data list
            self.data.append(email_item_data)
            # Set the selected index to the newly added item
            self.selected_email_index = len(self.data) - 1
            message = "đã thêm" # Update message


        # Save the entire data list to file (handles encryption)
        self._save_data()

        # Refresh UI after saving
        if self.current_view == "search":
             # If in search view, clear the search to show updated data in normal view
             self.clear_search()
        else:
            # In normal view, refresh the email list and re-select the saved/added email
            saved_email_index = self.selected_email_index # Store index before refresh potentially changes it
            self.refresh_email_list() # Repopulates the email treeview

            # Try to re-select the email in the treeview based on its email address
            item_id_to_select = None
            if saved_email_index is not None and 0 <= saved_email_index < len(self.data):
                 email_to_reselect = self.data[saved_email_index].get("email", "")
                 for item_id in self.email_tree.get_children():
                    values = self.email_tree.item(item_id, 'values')
                    # Compare email address (case-insensitive)
                    if values and values[0].lower() == email_to_reselect.lower():
                        item_id_to_select = item_id
                        break # Found the item

            if item_id_to_select:
                 # Select the item and make it visible
                 self.email_tree.selection_set(item_id_to_select)
                 self.email_tree.see(item_id_to_select)
                 # on_email_select will be triggered by selection_set and load details
            else:
                 # If re-selection failed (e.g., data somehow vanished), clear details
                 self.selected_email_index = None
                 self.clear_email_details()
                 self.clear_channel_details()
                 self.channel_tree.delete(*self.channel_tree.get_children())
                 self.update_channel_quick_view([])


        # Show success message to the user
        messagebox.showinfo("Thành công", f"Thông tin email {message}.", parent=self.root)

        # If a new email was added, automatically switch to the channel tab for easier channel addition
        if message == "đã thêm" and self.selected_email_index is not None:
             self.notebook.select(1)


    def add_email(self):
        """Prepares the UI to add a new email account."""
         # Kiểm tra xem ứng dụng có bị khóa không
        if self._is_locked:
            self.status_var.set("Ứng dụng đang bị khóa. Không thể thêm email.")
            return

        # Prompt to save if there are unsaved changes
        if self._data_changed:
             response = messagebox.askyesnocancel("Chưa lưu", "Bạn có muốn lưu các thay đổi trước khi thêm email mới không?", parent=self.root)
             if response is True:
                 self.save_email() # Attempt to save current data
                 # Note: If save_email fails, _data_changed will still be True.
                 # We proceed *only* if save was successful or user chose not to save.
                 if self._data_changed: # If save_email failed to clear the flag
                     messagebox.showwarning("Lưu thất bại", "Không lưu được dữ liệu hiện tại. Hủy thêm email.", parent=self.root)
                     return # Stop if save failed
             elif response is None:
                 return # User cancelled

        # Reset data changed flag
        self._data_changed = False

        # Clear current selection and details
        self.selected_email_index = None
        self.selected_channel_index = None
        self.clear_email_details()
        self.clear_channel_details()

        # Clear treeviews
        self.email_tree.selection_remove(self.email_tree.selection()) # Deselect in treeview
        self.channel_tree.delete(*self.channel_tree.get_children())
        self.update_channel_quick_view([])

        # Switch to the Email Details tab and focus the email entry field
        self.notebook.select(0)
        self.email_entry.focus_set()

        # Status update
        self.status_var.set("Sẵn sàng thêm email mới")


    def delete_email(self):
        """Deletes the currently selected email account and its channels."""
         # Kiểm tra xem ứng dụng có bị khóa không
        if self._is_locked:
            self.status_var.set("Ứng dụng đang bị khóa. Không thể xóa email.")
            return

        # Check if an email is selected
        if self.selected_email_index is None or not (0 <= self.selected_email_index < len(self.data)):
            messagebox.showwarning("Chọn", "Vui lòng chọn một tài khoản email để xóa.", parent=self.root)
            return

        # Get the email address for confirmation message
        email_to_delete = self.data[self.selected_email_index].get("email", "Không rõ")

        # Ask for confirmation
        if messagebox.askyesno("Xác nhận xóa", f"Bạn có chắc chắn muốn xóa tài khoản email '{email_to_delete}' và tất cả các kênh liên quan của nó không?\nThao tác này không thể hoàn tác.", parent=self.root):
            try:
                # Delete the email item from the data list
                del self.data[self.selected_email_index]

                # Save the modified data list
                self._save_data()

                # Reset selection indices
                self.selected_email_index = None
                self.selected_channel_index = None

                # Refresh UI after deletion
                if self.current_view == "search":
                    # Clear search view to return to normal view with updated data
                    self.clear_search()
                else:
                    # In normal view, refresh the email list treeview
                    self.refresh_email_list()
                    # Clear details forms and channel treeview/quick view
                    self.clear_email_details()
                    self.clear_channel_details()
                    self.channel_tree.delete(*self.channel_tree.get_children())
                    self.update_channel_quick_view([])

                self.status_var.set(f"Email '{email_to_delete}' đã bị xóa"); messagebox.showinfo("Thành công", "Đã xóa tài khoản email thành công.", parent=self.root)

            except Exception as e:
                # Handle errors during deletion or saving
                messagebox.showerror("Lỗi", f"Không xóa được tài khoản email: {e}", parent=self.root)


    def add_channel(self):
        """Prepares the UI to add a new channel for the selected email."""
         # Kiểm tra xem ứng dụng có bị khóa không
        if self._is_locked:
            self.status_var.set("Ứng dụng đang bị khóa. Không thể thêm kênh.")
            return

        # Check if an email is selected first
        if self.selected_email_index is None or not (0 <= self.selected_email_index < len(self.data)):
            messagebox.showwarning("Chọn", "Vui lòng chọn tài khoản email trước khi thêm kênh.", parent=self.root)
            self.notebook.select(0) # Chuyển sang tab email nếu no email is selected
            return

        # Clear current channel selection and details form
        self.selected_channel_index = None
        self.clear_channel_details()

        # Switch to the Channel Management tab and focus the URL entry field
        self.notebook.select(1)
        self.url_entry.focus_set()

        email_addr = self.data[self.selected_email_index].get('email', 'đã chọn')
        self.status_var.set(f"Sẵn sàng thêm kênh cho {email_addr}")


    def check_channel_url_exists(self, url, exclude_email_idx=None, exclude_channel_idx=None):
        """Kiểm tra xem URL kênh có tồn tại trong dữ liệu không, loại trừ một kênh cụ thể nếu cần."""
        target_url_lower = url.lower()

        # Lặp qua tất cả các tài khoản email
        for email_idx, email_data in enumerate(self.data):
            is_current_email = (email_idx == exclude_email_idx)
            channels_list = email_data.get("channels", [])
            if channels_list is None: channels_list = [] # Ensure it's a list

            # Lặp qua các kênh trong email hiện tại
            for ch_idx, channel in enumerate(channels_list):
                # Nếu đang kiểm tra kênh đang chọn trong khi cập nhật, loại trừ nó khỏi kiểm tra trùng lặp
                if is_current_email and ch_idx == exclude_channel_idx:
                    continue

                # So sánh URL kênh (không phân biệt chữ hoa chữ thường)
                if channel.get("channel_url", "").lower() == target_url_lower:
                    # Tìm thấy URL trùng lặp, trả về email và tên kênh
                    return email_data.get("email", "Không rõ"), channel.get("channel_name", "Không tên")

        # Không tìm thấy trùng lặp
        return None, None


    def save_channel(self):
        """Lưu chi tiết kênh hiện tại từ biểu mẫu vào danh sách kênh của email đã chọn."""
         # Kiểm tra xem ứng dụng có bị khóa không
        if self._is_locked:
            self.status_var.set("Ứng dụng đang bị khóa. Không thể lưu.")
            return

        # Check if an email is selected
        if self.selected_email_index is None or not (0 <= self.selected_email_index < len(self.data)):
            messagebox.showwarning("Lỗi", "Vui lòng chọn tài khoản email trước khi lưu kênh.", parent=self.root)
            self.notebook.select(0) # Chuyển sang tab email
            return

        # Lấy dữ liệu từ các trường biểu mẫu
        url = self.url_entry.get().strip()
        name = self.name_entry.get().strip()
        note = self.note_entry.get().strip()
        use = self.use_var.get()

        # Reset style lỗi trước khi xác thực lại
        self.url_entry.config(style='TEntry')


        # Thực hiện xác thực cơ bản
        if not url:
            messagebox.showwarning("Thiếu thông tin", "URL kênh là bắt buộc.", parent=self.root)
            self.url_entry.config(style='Error.TEntry')
            self.url_entry.focus_set()
            return

        # Xác thực định dạng URL, đề xuất thêm https:// nếu thiếu
        if not self.validate_url(url):
             if messagebox.askyesno("Định dạng URL", "Định dạng URL có vẻ không đúng. Bạn có muốn thử thêm tiền tố 'https://' không?", parent=self.root):
                 url_before_fix = url # Lưu URL gốc để so sánh
                 # Thêm https:// và xóa http/https nếu đã có để tránh tiền tố kép
                 url = "https://" + url.replace("http://", "").replace("https://", "")
                 self.url_entry.delete(0, tk.END)
                 self.url_entry.insert(0, url)
                 # Re-validate after suggesting fix - maybe redundant, but safer
                 if not self.validate_url(url):
                     messagebox.showwarning("URL không hợp lệ", "Định dạng URL vẫn không hợp lệ sau khi sửa.", parent=self.root)
                     self.url_entry.config(style='Error.TEntry')
                     self.url_entry.focus_set()
                     return
                 elif url == url_before_fix:
                     # If the fix didn't change anything (e.g. typing 'invalid-url')
                     messagebox.showwarning("URL không hợp lệ", "Định dạng URL không hợp lệ.", parent=self.root)
                     self.url_entry.config(style='Error.TEntry')
                     self.url_entry.focus_set()
                     return

             else:
                 messagebox.showwarning("URL không hợp lệ", "Định dạng URL không hợp lệ.", parent=self.root)
                 self.url_entry.config(style='Error.TEntry')
                 self.url_entry.focus_set()
                 return

        # Reset style if validation is successful
        self.url_entry.config(style='TEntry')

        # Check for duplicate channel URL, excluding the current channel if updating
        index_to_exclude = self.selected_channel_index # Pass the original index of the current channel if updating
        existing_email, existing_name = self.check_channel_url_exists(url, self.selected_email_index, index_to_exclude)

        if existing_email:
            # Ask for confirmation if a duplicate URL is found
            if not messagebox.askyesno("URL Trùng lặp", f"URL Kênh này đã tồn tại dưới email '{existing_email}' (Kênh: '{existing_name}').\nBạn có muốn lưu mục trùng lặp này không?", parent=self.root):
                 return # User chose not to save duplicate


        # Prepare channel data dictionary
        channel_data = {"channel_url": url, "channel_name": name, "note": note, "in_use": use}

        # Get the channels list for the selected email, ensure it exists
        channels_list = self.data[self.selected_email_index].setdefault("channels", [])
        # setdefault ensures 'channels' key exists and is a list; check again in case it was None
        if channels_list is None:
             channels_list = self.data[self.selected_email_index]["channels"] = []


        message = "đã cập nhật" # Default message
        # Check if we are updating an existing channel or adding a new one
        if self.selected_channel_index is not None and 0 <= self.selected_channel_index < len(channels_list):
            # If updating, replace the channel data at the stored original index
            channels_list[self.selected_channel_index] = channel_data
        else:
            # If adding a new channel, append it to the list
            channels_list.append(channel_data)
            # Reset selected channel index as we are no longer specifically selecting the added one
            self.selected_channel_index = None
            message = "đã thêm" # Update message


        # Save the entire data list to file (handles encryption)
        self._save_data()

        # Refresh UI after saving
        if self.current_view == "search":
             # Clear search view to return to normal view with updated data
             self.clear_search()
        else:
            # In normal view, update the channel list treeview for the selected email
            email_idx_before = self.selected_email_index # Store email index before refresh
            self.update_channel_list() # Repopulates channel treeview and quick view

            # Refresh the main email list to update channel counts or tags
            self.refresh_email_list()

            # Attempt to re-select the email in the email treeview after refresh
            if email_idx_before is not None and 0 <= email_idx_before < len(self.data):
                 email_to_reselect = self.data[email_idx_before].get("email")
                 item_id_to_select = None
                 for item_id in self.email_tree.get_children():
                     values = self.email_tree.item(item_id, 'values')
                     if values and values[0] == email_to_reselect:
                         item_id_to_select = item_id
                         break
                 if item_id_to_select:
                     self.email_tree.selection_set(item_id_to_select)
                     self.email_tree.see(item_id_to_select)
                     # on_email_select will be triggered by selection_set

            # Clear the channel details form and reset selected channel index
            self.clear_channel_details()
            self.selected_channel_index = None


        # Update status bar and show success message
        email_addr = self.data[self.selected_email_index].get('email', '...') if self.selected_email_index is not None else '...'
        self.status_var.set(f"Kênh {message} cho {email_addr}")
        messagebox.showinfo("Thành công", f"Kênh {message} thành công.", parent=self.root)


    def delete_channel(self):
        """Xóa kênh hiện đang chọn khỏi danh sách kênh của email đã chọn."""
         # Kiểm tra xem ứng dụng có bị khóa không
        if self._is_locked:
            self.status_var.set("Ứng dụng đang bị khóa. Không thể xóa kênh.")
            return

        # Check if an email is selected
        if self.selected_email_index is None or not (0 <= self.selected_email_index < len(self.data)):
            messagebox.showwarning("Chọn Email", "Vui lòng chọn tài khoản email trước.", parent=self.root)
            return

        # Check if a channel is selected in the channel treeview
        selected_items = self.channel_tree.selection()
        if not selected_items:
            messagebox.showwarning("Chọn Kênh", "Vui lòng chọn một kênh để xóa khỏi danh sách.", parent=self.root)
            return

        # Get the index of the selected item in the treeview
        tree_idx = self.channel_tree.index(selected_items[0])

        index_in_data = None # This will be the actual index in the email's channel list in self.data
        name = "kênh đang chọn" # Default name for confirmation message

        channels_list_full = self.data[self.selected_email_index].get("channels", [])
        if channels_list_full is None: channels_list_full = [] # Ensure it's a list

        # Determine the actual index in the underlying data list based on the current view
        if self.current_view == "search":
             # In search view, the treeview index maps to an item in search_result["channel_matches"]
             search_result = next((sr for sr in self.search_results if sr["email_idx"] == self.selected_email_index), None)

             if search_result and 0 <= tree_idx < len(search_result["channel_matches"]):
                  # Get the original index and data of the channel from the search result
                  index_in_data, data_to_delete = search_result["channel_matches"][tree_idx]
                  name = data_to_delete.get("channel_name", name) # Get the channel name for confirmation
             else:
                  # Should not happen if treeview populated correctly
                  messagebox.showerror("Lỗi", "Không tìm thấy kênh trong kết quả tìm kiếm để xóa.", parent=self.root)
                  return
        else: # Normal view
             # In normal view, the treeview index maps to an item in self.current_channels (the displayed list)
             # We need the index of this channel in the *original* full list for deletion.
             channels_list_in_view = self.current_channels # This is the list currently in the treeview

             if 0 <= tree_idx < len(channels_list_in_view):
                 channel_to_delete_data = channels_list_in_view[tree_idx]
                 name = channel_to_delete_data.get("channel_name", name) # Get name for confirmation

                 # Find the index of this specific channel_to_delete_data item within the *original* full list
                 try:
                     # Find the index of the current channel_data dict within the original full list (by reference)
                     index_in_data = next(i for i, ch in enumerate(channels_list_full) if ch is channel_to_delete_data)
                 except StopIteration:
                     # Should not happen if data consistency is maintained
                     messagebox.showerror("Lỗi Nội bộ", "Không tìm thấy kênh trong danh sách dữ liệu gốc để xóa.", parent=self.root)
                     return
             else:
                  # Should not happen if treeview populated correctly
                  messagebox.showerror("Lỗi", "Không tìm thấy chỉ mục kênh ở chế độ xem thông thường để xóa.", parent=self.root)
                  return

        # Ask for confirmation before deleting
        if messagebox.askyesno("Xác nhận xóa", f"Bạn có chắc chắn muốn xóa kênh '{name}' không?", parent=self.root):
            # Ensure the calculated index is valid before attempting deletion
            if index_in_data is not None and 0 <= index_in_data < len(channels_list_full):
                try:
                    # Delete the channel from the email's original channels list
                    del channels_list_full[index_in_data]

                    # Save the modified data list
                    self._save_data()

                    # Refresh UI after deletion
                    if self.current_view == "search":
                         # Clear search view to return to normal view with updated data
                         self.clear_search()
                    else:
                        # In normal view, update the channel list treeview for the selected email
                        email_idx_before = self.selected_email_index # Store email index
                        self.update_channel_list() # Repopulates channel treeview and quick view

                        # Refresh the main email list to update channel counts
                        self.refresh_email_list()

                        # Attempt to re-select the email after refresh
                        if email_idx_before is not None and 0 <= email_idx_before < len(self.data):
                            email_to_reselect = self.data[email_idx_before].get("email")
                            item_id_to_select = None
                            for item_id in self.email_tree.get_children():
                                values = self.email_tree.item(item_id, 'values')
                                if values and values[0] == email_to_reselect:
                                    item_id_to_select = item_id
                                    break
                            if item_id_to_select:
                                self.email_tree.selection_set(item_id_to_select)
                                self.email_tree.see(item_id_to_select)
                                # on_email_select will be triggered

                    # Clear the channel details form and reset selected channel index
                    self.clear_channel_details()
                    self.selected_channel_index = None

                    self.status_var.set(f"Kênh '{name}' đã bị xóa"); messagebox.showinfo("Thành công", "Đã xóa kênh thành công.", parent=self.root)

                except Exception as e:
                    # Handle errors during deletion or saving
                    messagebox.showerror("Lỗi", f"Không xóa được kênh: {e}", parent=self.root)
            else:
                 # Should not happen if checks above pass, but defensive
                 messagebox.showerror("Lỗi", "Chỉ mục xóa không hợp lệ sau xác nhận.", parent=self.root)


    def fetch_channel_name(self):
        """Lấy tên kênh từ URL được nhập trong biểu mẫu kênh."""
         # Kiểm tra xem ứng dụng có bị khóa không
        if self._is_locked:
            self.status_var.set("Ứng dụng đang bị khóa. Không thể lấy tên kênh.")
            return

        url = self.url_entry.get().strip()

        # Xác thực nhập liệu URL
        if not url:
            messagebox.showwarning("Thiếu URL", "Vui lòng nhập URL để lấy tên.", parent=self.root)
            self.url_entry.config(style='Error.TEntry') # Highlight error
            self.url_entry.focus_set()
            return

        # Xác thực định dạng URL, đề xuất thêm https:// nếu thiếu
        if not self.validate_url(url):
             if messagebox.askyesno("Định dạng URL", "Định dạng URL có vẻ không đúng. Bạn có muốn thử thêm tiền tố 'https://' không?", parent=self.root):
                 url_before_fix = url # Lưu URL gốc để so sánh
                 # Thêm https:// và xóa http/https nếu đã có để tránh tiền tố kép
                 url = "https://" + url.replace("http://", "").replace("https://", "")
                 self.url_entry.delete(0, tk.END)
                 self.url_entry.insert(0, url)
                 # Kiểm tra lại sau khi sửa
                 if not self.validate_url(url):
                     messagebox.showwarning("URL không hợp lệ", "Định dạng URL vẫn không hợp lệ sau khi sửa.", parent=self.root)
                     self.url_entry.config(style='Error.TEntry')
                     self.url_entry.focus_set()
                     return
                 elif url == url_before_fix:
                     # If the fix didn't change anything (e.g. typing 'invalid-url')
                     messagebox.showwarning("URL không hợp lệ", "Định dạng URL không hợp lệ.", parent=self.root)
                     self.url_entry.config(style='Error.TEntry')
                     self.url_entry.focus_set()
                     return

             else:
                 messagebox.showwarning("URL không hợp lệ", "Định dạng URL không hợp lệ.", parent=self.root)
                 self.url_entry.config(style='Error.TEntry')
                 self.url_entry.focus_set()
                 return

        # Reset style if validation is successful
        self.url_entry.config(style='TEntry')

        self.status_var.set("Đang lấy tên..."); # Cập nhật thanh trạng thái
        # self._data_changed = True # Mark data as potentially changed (user expects to save after fetch) - Removed this line as it only fetches name, doesn't change actual data yet

        # Start the fetching process in a separate thread so the UI remains responsive
        # Pass a reference to the root window so the thread can safely update the UI via root.after()
        threading.Thread(target=self._fetch_channel_name_threaded, args=(url, self.root), daemon=True).start()


    def _fetch_channel_name_threaded(self, url, root_ref):
        """Thread function to fetch the channel name from a URL."""
        try:
            # Use requests to get the page content
            headers = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36"} # Add a User-Agent
            r = requests.get(url, headers=headers, timeout=10) # Add a timeout
            r.raise_for_status() # Raise HTTPError for bad responses (4xx or 5xx)

            # Use BeautifulSoup to parse the HTML
            soup = BeautifulSoup(r.text, "html.parser")

            # Try to find title using og:title meta tag (common for social media, often more accurate)
            title = None
            og_title = soup.find("meta", property="og:title")
            if og_title:
                 title = og_title.get("content")

            # If og:title not found, try the standard <title> tag
            if not title:
                title_tag = soup.find("title")
                if title_tag and title_tag.text:
                    # Clean up common suffixes like " - YouTube" or "| YouTube"
                    title = title_tag.text.strip().replace(" - YouTube", "").replace("| YouTube", "").strip()

            # Determine the final title or a default message
            final_title = title if title else "Không tìm thấy tên kênh"

            # Update the UI (name entry and status bar) on the main thread
            if root_ref and root_ref.winfo_exists():
                 # Clear the name entry and insert the fetched title
                 self.root.after(0, lambda: self.name_entry.delete(0, tk.END))
                 self.root.after(0, lambda t=final_title: self.name_entry.insert(0, t))

                 if title:
                     self.root.after(0, lambda: self.status_var.set("Đã lấy tên kênh. Nhớ Lưu Kênh."))
                 else:
                      self.root.after(0, lambda: self.status_var.set("Không tìm thấy tên kênh cho URL này."))

        except requests.exceptions.Timeout:
             # Handle request timeout error
             if root_ref and root_ref.winfo_exists():
                 self.root.after(0, lambda: self.status_var.set("Lỗi: Yêu cầu lấy tên đã hết thời gian chờ."))
                 print(f"Timeout when fetching name for URL: {url}")
        except requests.exceptions.RequestException as e:
             # Handle other request errors (e.g., connection errors, HTTP errors)
             if root_ref and root_ref.winfo_exists():
                 self.root.after(0, lambda s=f"Lỗi khi lấy tên: {e}": self.status_var.set(s))
                 print(f"Request error for URL {url}: {e}")
        except Exception as e:
             # Handle any other unexpected errors during parsing or processing
             if root_ref and root_ref.winfo_exists():
                 self.root.after(0, lambda s=f"Đã xảy ra lỗi: {e}": self.status_var.set(s))
                 print(f"Unexpected error when fetching name for URL {url}: {e}")


    def copy_otp(self):
        """Sao chép mã OTP hiện tại vào clipboard."""
         # Kiểm tra xem ứng dụng có bị khóa không
        if self._is_locked:
            self.status_var.set("Ứng dụng đang bị khóa. Không thể sao chép OTP.")
            return

        key = self.key_entry.get().strip().replace(" ", "").upper() # Lấy và làm sạch khóa

        if not key:
            messagebox.showwarning("Thiếu", "Chưa nhập khóa 2FA.", parent=self.root)
            self.status_var.set("Không có khóa để tạo OTP")
            return

        # Xác thực khóa trước khi cố gắng tạo OTP
        if not self.validate_2fa_key(key):
            messagebox.showwarning("Không hợp lệ", "Định dạng khóa 2FA không hợp lệ.", parent=self.root)
            self.status_var.set("Khóa không hợp lệ")
            self.key_entry.config(style='Error.TEntry') # Highlight error
            return

        # Reset style nếu khóa hợp lệ
        self.key_entry.config(style='TEntry')

        try:
            # Tạo mã OTP hiện tại và sao chép vào clipboard
            otp_code = pyotp.TOTP(key).now()
            pyperclip.copy(otp_code)
            self.status_var.set("Đã sao chép OTP vào clipboard")
        except Exception as e:
            # Xử lý lỗi trong quá trình tạo hoặc sao chép OTP
            self.status_var.set("Lỗi OTP")
            messagebox.showerror("Lỗi", f"Không tạo hoặc sao chép được OTP: {e}", parent=self.root)


    def copy_channel_url(self):
        """Sao chép URL của kênh được chọn trong treeview kênh vào clipboard."""
         # Kiểm tra xem ứng dụng có bị khóa không
        if self._is_locked:
            self.status_var.set("Ứng dụng đang bị khóa. Không thể sao chép.")
            return

        selected_items = self.channel_tree.selection()

        if not selected_items:
            messagebox.showwarning("Chọn", "Vui lòng chọn một kênh từ danh sách để sao chép URL của nó.", parent=self.root)
            return

        # Lấy các giá trị của mục được chọn
        item_values = self.channel_tree.item(selected_items[0], 'values')

        # URL expected to be the 3rd value (index 2)
        if item_values and len(item_values) > 2 and item_values[2]:
             url = item_values[2]
             pyperclip.copy(url)
             self.status_var.set(f"Đã sao chép URL: {url}")
        else:
             messagebox.showwarning("Lỗi", "Không tìm thấy URL kênh cho mục đã chọn.", parent=self.root)


    # --- Phương thức QR Code ---
    def display_qrcode_image_preview(self, base64_string):
        """Hiển thị xem trước ảnh mã QR từ một chuỗi base64, chỉ hiển thị QR đen trên nền trắng."""
        # Xóa ảnh và văn bản trước đó
        self.qrcode_image_label.config(image='', text="Chưa lưu ảnh mã QR nào", compound=tk.TOP)
        self.qrcode_photo_image = None  # Xóa tham chiếu đến ảnh trước đó

        # Không làm gì nếu không có chuỗi base64 hoặc thư viện QR không có sẵn
        if not base64_string or not HAS_QR_LIBS:
            return

        try:
            # Giải mã chuỗi base64 thành bytes, sau đó mở dưới dạng Image
            img_bytes = base64.b64decode(base64_string)
            img = Image.open(io.BytesIO(img_bytes))

            # Chuyển ảnh sang đen trắng (mode '1' for 1-bit pixels)
            img = img.convert('1')

            # Tìm vị trí của QR code trong ảnh (nếu có)
            decoded = pyzbar.decode(img)
            if decoded:
                # Lấy tọa độ của QR code đầu tiên tìm thấy
                rect = decoded[0].rect
                left, top, width, height = rect.left, rect.top, rect.width, rect.height

                # Mở rộng biên một chút (10% kích thước QR code)
                padding = int(min(width, height) * 0.1)
                left = max(0, left - padding)
                top = max(0, top - padding)
                right = min(img.width, left + width + 2*padding)
                bottom = min(img.height, top + height + 2*padding)

                # Cắt ảnh chỉ lấy phần QR code
                img = img.crop((left, top, right, bottom))

            # Tạo ảnh nền trắng với kích thước cố định 200x200
            final_size = 200
            bg = Image.new('RGB', (final_size, final_size), 'white')

            # Tính toán vị trí đặt QR code vào giữa nền trắng
            img.thumbnail((final_size - 20, final_size - 20))  # Giữ chừa lề 10px mỗi bên
            offset = ((final_size - img.width) // 2, (final_size - img.height) // 2)

            # Dán QR code lên nền trắng
            bg.paste(img, offset)

            # Chuyển đổi PIL Image sang Tkinter PhotoImage
            tk_img = ImageTk.PhotoImage(bg)

            # Cập nhật nhãn với ảnh và văn bản
            self.qrcode_image_label.config(image=tk_img, text="Mã QR", compound=tk.TOP)
            self.qrcode_photo_image = tk_img  # Giữ tham chiếu để ngăn garbage collection

        except Exception as e:
            # Xử lý bất kỳ lỗi nào trong quá trình xử lý hoặc hiển thị ảnh
            print(f"Lỗi hiển thị xem trước QR: {e}")
            self.qrcode_image_label.config(image='', text="Lỗi khi tải ảnh QR", compound=tk.TOP, foreground="#e74c3c")


    def load_qrcode_image(self):
        """Nhắc người dùng chọn file ảnh và tải nó làm xem trước mã QR."""
         # Kiểm tra xem ứng dụng có bị khóa không
        if self._is_locked:
            self.status_var.set("Ứng dụng đang bị khóa. Không thể tải ảnh QR.")
            return
        # Kiểm tra xem thư viện QR có sẵn không
        if not HAS_QR_LIBS:
             messagebox.showwarning("Thiếu Thư viện", "Cần có thư viện Pillow và pyzbar cho chức năng mã QR.", parent=self.root)
             return

        # Kiểm tra xem email có được chọn để liên kết ảnh không
        if self.selected_email_index is None or not (0 <= self.selected_email_index < len(self.data)):
            messagebox.showwarning("Chọn", "Vui lòng chọn tài khoản email trước.", parent=self.root)
            return

        # Open save file dialog to select an image file
        file_path = filedialog.askopenfilename(
            title="Chọn File ảnh mã QR",
            filetypes=(("File ảnh", "*.png *.jpg *.jpeg *.gif *.bmp"), ("Tất cả file", "*.*")),
            parent=self.root # Make dialog transient
        )

        if not file_path:
            return # User cancelled

        try:
            # Read the image bytes from the file
            with open(file_path, "rb") as f:
                 image_bytes = f.read()

            # Optional: Verify image format without loading full pixel data
            # Image.open(io.BytesIO(image_bytes)).verify()

            # Convert image bytes to base64 string
            base64_string = base64.b64encode(image_bytes).decode('ascii')

            # Store the base64 string in the variable (will be encrypted on save)
            self.qrcode_image_base64_decrypted_var.set(base64_string)

            # Display the preview
            self.display_qrcode_image_preview(base64_string)

            # Mark data as changed, prompting user to save
            self._data_changed = True
            self.status_var.set(f"Đã tải ảnh QR: {os.path.basename(file_path)}. Nhớ Lưu Email.")

            # Offer to save immediately
            if messagebox.askyesno("Lưu?", "Đã tải ảnh mã QR thành công. Bạn có muốn lưu email ngay bây giờ không?", parent=self.root):
                 self.save_email() # Call save_email if user confirms

        except (IOError, FileNotFoundError, Image.UnidentifiedImageError) as e:
            # Handle specific image file errors
            messagebox.showerror("Lỗi File", f"Không tải được file ảnh: {e}", parent=self.root)
            self.status_var.set("Lỗi khi tải ảnh QR.")
        except Exception as e:
            # Handle any other unexpected errors
            messagebox.showerror("Lỗi", f"Đã xảy ra lỗi không mong muốn trong khi tải ảnh: {e}", parent=self.root)
            self.status_var.set("Lỗi khi tải ảnh QR.")


    def scan_qrcode_image(self):
        """Nhắc người dùng chọn file ảnh và quét nó để tìm khóa 2FA."""
         # Kiểm tra xem ứng dụng có bị khóa không
        if self._is_locked:
            self.status_var.set("Ứng dụng đang bị khóa. Không thể quét ảnh QR.")
            return

        # Check if QR libraries are available
        if not HAS_QR_LIBS:
             messagebox.showwarning("Thiếu Thư viện", "Cần có thư viện Pillow và pyzbar cho chức năng mã QR.", parent=self.root)
             return

        # Check if an email is selected
        if self.selected_email_index is None or not (0 <= self.selected_email_index < len(self.data)):
            messagebox.showwarning("Chọn", "Vui lòng chọn tài khoản email trước.", parent=self.root)
            return

        # Open file dialog to select an image file
        file_path = filedialog.askopenfilename(
            title="Chọn File ảnh mã QR để quét",
            filetypes=(("File ảnh", "*.png *.jpg *.jpeg *.gif *.bmp"), ("Tất cả file", "*.*")),
            parent=self.root # Make dialog transient
        )

        if not file_path:
            return # User cancelled

        self.status_var.set(f"Đang quét {os.path.basename(file_path)}..."); # Update status bar
        self._data_changed = True # Scanning might lead to a change (key extraction)

        # Start the scanning process in a separate thread so the UI remains responsive
        threading.Thread(target=self._scan_qrcode_image_threaded, args=(file_path, self.root), daemon=True).start()


    def _scan_qrcode_image_threaded(self, file_path, root_ref):
        """Thread function to scan an image file for QR code data."""
        try:
            # Open the image file
            with open(file_path, "rb") as f:
                 image_bytes = f.read()
            img = Image.open(io.BytesIO(image_bytes))

            # Decode QR codes in the image
            decoded = pyzbar.decode(img)

            if not decoded:
                # No QR code found in the image
                if root_ref and root_ref.winfo_exists():
                     self.root.after(0, lambda: self.status_var.set("Không tìm thấy mã QR trong ảnh."))
                return

            # Get data from the first detected QR code
            qr_data = decoded[0].data.decode('utf-8')
            key = None # Variable to hold the extracted 2FA key

            # Attempt to parse the data as a URI (e.g., otpauth://...)
            try:
                 uri = pyotp.parse_uri(qr_data)
                 key = uri.secret # Extract the secret key from URI
                 # Optional: Extract issuer/account name if present
                 # issuer = uri.issuer
                 # account = uri.name
                 print(f"Đã trích xuất URI Khóa 2FA. Secret: {key}")
            except Exception:
                 # If not a valid URI, check if it's a valid Base32 key directly
                 if self.validate_2fa_key(qr_data):
                      key = qr_data.strip().replace(" ", "").upper() # Use the data as the key
                      print(f"Đã trích xuất Khóa 2FA Base32. Key: {key}")


            if key:
                # Key successfully extracted
                if root_ref and root_ref.winfo_exists():
                     # Update the 2FA key entry field on the main thread
                     # Reset style in case it was marked as invalid
                     self.root.after(0, lambda: self.key_entry.config(style='TEntry'))
                     self.root.after(0, lambda k=key: (self.key_entry.delete(0, tk.END), self.key_entry.insert(0, k)))
                     self.root.after(0, lambda: self.status_var.set("Đã trích xuất Khóa 2FA. Nhớ Lưu Email."))

                     # Ask user if they also want to save the QR image
                     if messagebox.askyesno("Lưu ảnh?", "Đã trích xuất Khóa 2FA thành công. Bạn có muốn lưu cả ảnh QR cùng với email không?", parent=self.root):
                         # Convert image bytes to base64 string and store in the variable
                         base64_string = base64.b64encode(image_bytes).decode('ascii')
                         self.root.after(0, lambda b64=base64_string: self.qrcode_image_base64_decrypted_var.set(b64))
                         # Display the preview of the loaded image
                         self.root.after(0, lambda b64=base64_string: self.display_qrcode_image_preview(b64))

                         # Ask user if they want to save the email (with the key and image)
                         if messagebox.askyesno("Lưu Email?", "Đã thêm mã QR và khóa. Bạn có muốn lưu chi tiết email ngay bây giờ không?", parent=self.root):
                              self.root.after(0, lambda: self.save_email()) # Call save_email on the main thread
                     else:
                          # User didn't want to save the image, ensure preview is cleared
                          self.root.after(0, lambda: self.clear_qrcode_image_variable())

            else:
                # QR code found but could not extract a valid 2FA key from it
                if root_ref and root_ref.winfo_exists():
                    self.root.after(0, lambda: self.status_var.set("Tìm thấy mã QR, nhưng không trích xuất được dữ liệu khóa 2FA hợp lệ."))

        except (IOError, FileNotFoundError, Image.UnidentifiedImageError) as e:
            # Handle specific image file errors in the thread
            print(f"Lỗi ảnh luồng: {e}")
            if root_ref and root_ref.winfo_exists():
                self.root.after(0, lambda err=e: self.status_var.set(f"Lỗi file ảnh trong khi quét: {err}"))
        except Exception as e:
            # Handle any other unexpected errors in the thread
            print(f"Lỗi quét luồng: {e}")
            if root_ref and root_ref.winfo_exists():
                self.root.after(0, lambda err=e: self.status_var.set(f"Đã xảy ra lỗi trong khi quét: {err}"))

    def clear_qrcode_image(self):
        """Xóa ảnh mã QR đã lưu cho email đã chọn."""
         # Kiểm tra xem ứng dụng có bị khóa không
        if self._is_locked:
            self.status_var.set("Ứng dụng đang bị khóa. Không thể xóa ảnh QR.")
            return

        # Check if an email is selected
        if self.selected_email_index is None or not (0 <= self.selected_email_index < len(self.data)):
            messagebox.showwarning("Chọn", "Vui lòng chọn tài khoản email trước.", parent=self.root)
            return

        # Check if there is actually an image stored
        if not self.qrcode_image_base64_decrypted_var.get():
            messagebox.showinfo("Không có ảnh", "Hiện tại không có ảnh mã QR nào được lưu cho email này.", parent=self.root)
            return

        # Ask for confirmation before clearing
        if messagebox.askyesno("Xác nhận xóa", "Bạn có chắc chắn muốn xóa ảnh mã QR đã lưu cho tài khoản email này không?\nBạn phải 'Lưu Email' để thay đổi này là vĩnh viễn.", parent=self.root):
            # Clear the variable and update the preview
            self.clear_qrcode_image_variable()
            # Mark data as changed, requiring a save
            self._data_changed = True
            self.status_var.set("Đã xóa ảnh mã QR. Nhớ Lưu Email.")

    def clear_qrcode_image_variable(self):
         """Xóa biến base64 mã QR và cập nhật nhãn xem trước."""
         self.qrcode_image_base64_decrypted_var.set("") # Clear the string variable
         # Reset the preview label
         self.qrcode_image_label.config(image='', text="Chưa lưu ảnh mã QR nào", compound=tk.TOP)
         self.qrcode_photo_image = None # Clear the image reference


    # --- Import/Export Excel Methods ---
    def export_to_excel(self):
        """Exports the current decrypted data to an Excel (.xlsx) file."""
         # Kiểm tra xem ứng dụng có bị khóa không
        if self._is_locked:
            self.status_var.set("Ứng dụng đang bị khóa. Không thể xuất dữ liệu.")
            return

        if not self.data:
            messagebox.showinfo("Không có dữ liệu", "Không có dữ liệu để xuất.", parent=self.root)
            return

        # Open save file dialog
        file_path = filedialog.asksaveasfilename(
            title="Xuất Dữ liệu ra Excel",
            defaultextension=".xlsx", # Default file extension
            filetypes=[("File Excel", "*.xlsx"), ("Tất cả file", "*.*")], # Allowed file types
            parent=self.root # Make dialog transient
        )

        if not file_path:
            return # User cancelled

        try:
            # Create a new workbook and select the active worksheet
            wb = openpyxl.Workbook()
            ws = wb.active
            ws.title = "Email_Channel_Data" # Worksheet title

            # Define the header row
            headers = [
                "Email", "Password", "Recovery Email", "Recovery Password", "Recovery Phone", "Email Note",
                "2FA Key", # Thêm 2FA Key vào header
                "Is Verified", "Verification Failed", "Verified By", "Login Location",
                "QR Code Image (Base64)", # Note: This is the raw base64 string
                "Channel URL", "Channel Name", "Channel Note", "Channel In Use"
            ]
            ws.append(headers) # Write headers to the first row

            # Write data rows
            for item in self.data:
                # Extract email-level data
                email = item.get("email", "")
                password = item.get("password", "") # This data is already decrypted when loaded
                recovery_email = item.get("recovery_email", "")
                # === LẤY DỮ LIỆU TRƯỜNG MỚI ĐỂ XUẤT ===
                recovery_password = item.get("recovery_password", "")
                recovery_phone = item.get("recovery_phone", "")
                email_note = item.get("email_note", "") # Lấy ghi chú email

                key = item.get("2fa_key", "") # Lấy 2FA Key

                is_verified = item.get("is_verified", False)
                verification_failed = item.get("verification_failed", False)
                verified_by = item.get("verified_by", "")
                login_location = item.get("login_location", "")
                qrcode_img = item.get("qrcode_image_base64", "")

                channels = item.get("channels", [])
                if channels is None: channels = [] # Ensure it's a list

                if not channels:
                    # If an email has no channels, export one row with email data and empty channel fields
                    ws.append([
                        email,
                        password,
                        recovery_email,
                        # === XUẤT TRƯỜNG MỚI ===
                        recovery_password,
                        recovery_phone,
                        email_note,

                        key, # Xuất 2FA Key
                        is_verified,
                        verification_failed,
                        verified_by,
                        login_location,
                        qrcode_img,
                        "", "", "", "" # Empty channel fields
                    ])
                else:
                    # If an email has channels, export one row for each channel, duplicating email data
                    for ch in channels:
                        ws.append([
                            email,
                            password,
                            recovery_email,
                             # === XUẤT TRƯỜNG MỚI ===
                            recovery_password,
                            recovery_phone,
                            email_note,

                            key, # Xuất 2FA Key
                            is_verified,
                            verification_failed,
                            verified_by,
                            login_location,
                            qrcode_img,
                            ch.get("channel_url", ""),
                            ch.get("channel_name", ""),
                            ch.get("note", ""),
                            ch.get("in_use", False),
                        ])

            # Auto-adjust column widths for better readability in Excel
            for col in ws.columns:
                max_length = 0
                col_letter = get_column_letter(col[0].column) # Get column letter (A, B, C, ...)
                # Calculate max length of content in the column
                for cell in col:
                    val = str(cell.value) if cell.value is not None else ""
                    max_length = max(max_length, len(val))
                # Set adjusted width ( heuristic: max_length + padding)
                # Limit max width to avoid excessively wide columns for long text/base64
                adjusted_width = min((max_length + 2) * 1.2, 80) # Max width 80 for readability
                ws.column_dimensions[col_letter].width = adjusted_width

            # Save the workbook to the selected file path
            wb.save(file_path)

            self.status_var.set(f"Đã xuất dữ liệu ra {file_path}")
            messagebox.showinfo("Xuất thành công", f"Đã xuất dữ liệu thành công ra:\n{file_path}", parent=self.root)

        except Exception as e:
            # Handle any errors during the export process
            messagebox.showerror("Lỗi Xuất dữ liệu", f"Không xuất được dữ liệu ra file Excel.\n{e}", parent=self.root)
            self.status_var.set("Lỗi khi xuất dữ liệu!")


    def import_from_excel(self):
        """Imports data from an Excel (.xlsx) file, replacing current data."""
         # Kiểm tra xem ứng dụng có bị khóa không
        if self._is_locked:
            self.status_var.set("Ứng dụng đang bị khóa. Không thể nhập dữ liệu.")
            return

        # Open file dialog to select an Excel file
        file_path = filedialog.askopenfilename(
            title="Chọn File Excel để nhập",
            filetypes=[("File Excel", "*.xlsx"), ("Tất cả file", "*.*")],
            parent=self.root # Make dialog transient
        )

        if not file_path:
            return # User cancelled

        # Warn user about unsaved changes before importing
        if self._data_changed:
            resp = messagebox.askyesnocancel("Thay đổi chưa lưu", "Bạn có thay đổi chưa lưu trong dữ liệu hiện tại. Bạn có muốn lưu chúng trước khi nhập không? Nhập dữ liệu sẽ ghi đè dữ liệu hiện có.", parent=self.root)
            if resp is True:
                self._save_data() # Save current data
                if self._data_changed: # Check if save was successful (flag reset by _save_data)
                     messagebox.showwarning("Lưu thất bại", "Không lưu được dữ liệu hiện tại. Hủy nhập dữ liệu.", parent=self.root)
                     return # Abort if save failed
            elif resp is None:
                return # Abort import if user cancelled save prompt


        try:
            # Load the workbook and select the active sheet
            wb = openpyxl.load_workbook(file_path)
            ws = wb.active

            # Read all rows as tuples of values
            rows = list(ws.iter_rows(values_only=True))

            # Check if the file is empty or has no data rows (headers + at least one data row)
            if not rows or len(rows) < 2:
                messagebox.showwarning("Lỗi Nhập dữ liệu", "File Excel trống hoặc không chứa hàng dữ liệu nào.", parent=self.root)
                return

            # Get headers from the first row
            headers = rows[0]

            # Define required columns based on our data structure (including the new one)
            required_headers = [
                "Email", "Password", "Recovery Email", "Recovery Password", "Recovery Phone", "Email Note",
                "2FA Key", # Thêm 2FA Key vào required_headers
                "Is Verified", "Verification Failed", "Verified By", "Login Location",
                "QR Code Image (Base64)", "Channel URL", "Channel Name", "Channel Note", "Channel In Use"
            ]

            # Check for missing required headers
            missing_headers = [h for h in required_headers if h not in headers]
            if missing_headers:
                # Chỉ đưa ra cảnh báo thay vì lỗi fatal nếu thiếu các cột MỚI, để tương thích ngược với các file cũ
                # Nếu thiếu cột email hoặc password, đó là lỗi nghiêm trọng hơn.
                critical_missing = [h for h in missing_headers if h in ("Email", "Password", "Recovery Email", "2FA Key", "Channel URL", "Channel Name")]
                if critical_missing:
                    messagebox.showwarning("Lỗi Nhập dữ liệu", f"File Excel thiếu các cột bắt buộc sau:\n{', '.join(critical_missing)}", parent=self.root)
                    return
                else:
                     # Cảnh báo nếu thiếu các cột không quá quan trọng nhưng mới
                     print(f"Cảnh báo nhập dữ liệu: File Excel thiếu các cột mới tùy chọn: {', '.join(missing_headers)}")


            # Create a mapping from header names to column indices for easy access
            # Use .get() for safety in case a header is unexpectedly missing despite the check
            idx_map = {col: headers.index(col) for col in required_headers if col in headers}

            imported_data = [] # List to build the new data structure
            temp_map = {}  # Dictionary to track emails and their index in imported_data (key = email.lower(), value = index)


            # Process data rows starting from the second row
            for row_idx, row in enumerate(rows[1:]):
                # Check if row has enough columns based on the headers found
                # Use len(headers) instead of len(required_headers) for robustness with older files
                if len(row) < len(headers):
                    print(f"Skipping row {row_idx + 2} due to insufficient columns based on headers found.")
                    continue # Skip rows that don't match expected column count


                # Extract data using the index map, providing default empty strings or False if column doesn't exist
                # Use .get(..., -1) to handle cases where a header is missing (index will be -1), then provide default value
                email = (row[idx_map.get("Email", -1)] or "").strip() if idx_map.get("Email", -1) != -1 else ""
                password = (row[idx_map.get("Password", -1)] or "") if idx_map.get("Password", -1) != -1 else ""
                recovery_email = (row[idx_map.get("Recovery Email", -1)] or "") if idx_map.get("Recovery Email", -1) != -1 else ""

                # === LẤY DỮ LIỆU TRƯỜNG MỚI KHI NHẬP ===
                recovery_password = (row[idx_map.get("Recovery Password", -1)] or "") if idx_map.get("Recovery Password", -1) != -1 else ""
                recovery_phone = (row[idx_map.get("Recovery Phone", -1)] or "") if idx_map.get("Recovery Phone", -1) != -1 else ""
                email_note = (row[idx_map.get("Email Note", -1)] or "") if idx_map.get("Email Note", -1) != -1 else ""


                key = (row[idx_map.get("2FA Key", -1)] or "") if idx_map.get("2FA Key", -1) != -1 else "" # Lấy 2FA Key

                # Convert boolean strings/numbers from Excel to Python booleans
                # Handle potential None/empty values from Excel as False
                is_verified = str(row[idx_map.get("Is Verified", -1)]).lower() in ('true', '1') if idx_map.get("Is Verified", -1) != -1 and row[idx_map["Is Verified"]] is not None else False
                verification_failed = str(row[idx_map.get("Verification Failed", -1)]).lower() in ('true', '1') if idx_map.get("Verification Failed", -1) != -1 and row[idx_map["Verification Failed"]] is not None else False

                verified_by = (row[idx_map.get("Verified By", -1)] or "") if idx_map.get("Verified By", -1) != -1 else ""
                login_location = (row[idx_map.get("Login Location", -1)] or "") if idx_map.get("Login Location", -1) != -1 else ""
                qrcode_img = (row[idx_map.get("QR Code Image (Base64)", -1)] or "") if idx_map.get("QR Code Image (Base64)", -1) != -1 else "" # This should be raw base64 string


                channel_url = (row[idx_map.get("Channel URL", -1)] or "").strip() if idx_map.get("Channel URL", -1) != -1 else ""
                channel_name = (row[idx_map.get("Channel Name", -1)] or "") if idx_map.get("Channel Name", -1) != -1 else ""
                channel_note = (row[idx_map.get("Channel Note", -1)] or "") if idx_map.get("Channel Note", -1) != -1 else ""
                channel_in_use = str(row[idx_map.get("Channel In Use", -1)]).lower() in ('true', '1') if idx_map.get("Channel In Use", -1) != -1 and row[idx_map["Channel In Use"]] is not None else False


                # Skip rows with no email address
                if not email:
                    print(f"Skipping row {row_idx + 2} due to missing email.") # +2 because rows start at 1, and we skip header
                    continue

                email_lower = email.lower()

                # Check if this email address has already been added to imported_data during this import
                if email_lower not in temp_map:
                    # This is a new email entry
                    email_item = {
                        "email": email,
                        "password": password,
                        "recovery_email": recovery_email,
                         # === BAO GỒM TRƯỜNG MỚI ===
                        "recovery_password": recovery_password, # Store raw password, _save_data will encrypt
                        "recovery_phone": recovery_phone,
                        "email_note": email_note, # Bao gồm ghi chú email

                        "2fa_key": key, # Bao gồm 2FA Key
                        "is_verified": is_verified,
                        "verification_failed": verification_failed,
                        "verified_by": verified_by,
                        "login_location": login_location,
                        "qrcode_image_base64": qrcode_img, # Store raw base64, will be encrypted when _save_data
                        "channels": [] # Initialize empty channel list
                    }
                    # Add the channel data if a channel URL is present in this row
                    if channel_url:
                        email_item["channels"].append({
                            "channel_url": channel_url,
                            "channel_name": channel_name,
                            "note": channel_note,
                            "in_use": channel_in_use
                        })

                    # Add the new email item to the imported data list
                    imported_data.append(email_item)
                    # Store the index of this new email item in the temporary map
                    temp_map[email_lower] = len(imported_data) - 1
                else:
                    # This email address already exists in the imported_data list
                    idx = temp_map[email_lower] # Get the index of the existing email item

                    # Add the channel data if a channel URL is present in the current row to the existing email item's channel list
                    if channel_url:
                        imported_data[idx]["channels"].append({
                            "channel_url": channel_url,
                            "channel_name": channel_name,
                            "note": channel_note,
                            "in_use": channel_in_use
                        })
                    # Optional: Update email-level fields if they are provided in this row.
                    # For simplicity and assuming first row has primary email info, we skip updating email-level fields here.
                    # If updating on subsequent rows is needed, add logic here to check and update non-empty fields.


            # Check if any valid data was imported
            if not imported_data:
                messagebox.showwarning("Kết quả Nhập dữ liệu", "Không tìm thấy mục email hợp lệ nào trong file Excel.", parent=self.root)
                return

            # Ask for final confirmation before overwriting current data
            if messagebox.askyesno("Xác nhận Nhập dữ liệu", f"Đã đọc thành công {len(imported_data)} tài khoản email từ Excel.\nViệc nhập dữ liệu sẽ thay thế TẤT CẢ dữ liệu hiện tại của bạn.\nBạn có muốn tiếp tục không?", parent=self.root):
                # Replace the current data with the imported data
                self.data = imported_data
                # Save the newly imported data (this will encrypt sensitive fields)
                self._save_data()

                # Refresh the UI to display the imported data
                self.refresh_email_list()
                # Clear details and channel list as selection is lost after replacing data
                self.clear_email_details()
                self.clear_channel_details()
                self.channel_tree.delete(*self.channel_tree.get_children())
                self.update_channel_quick_view([])

                self.status_var.set(f"Đã nhập {len(imported_data)} email từ Excel.")
                messagebox.showinfo("Nhập dữ liệu thành công", f"Đã nhập thành công {len(imported_data)} tài khoản email từ Excel.", parent=self.root)

        except FileNotFoundError:
             messagebox.showerror("Lỗi File", "Không tìm thấy file đã chọn.", parent=self.root)
             self.status_var.set("Nhập dữ liệu thất bại: Không tìm thấy file.")
        except openpyxl.utils.exceptions.InvalidFileException:
             messagebox.showerror("Lỗi File", "File đã chọn không phải là file Excel (.xlsx) hợp lệ.", parent=self.root)
             self.status_bar.set("Nhập dữ liệu thất bại: File Excel không hợp lệ.")
        except Exception as e:
            # Catch any other errors during the import process
            messagebox.showerror("Lỗi Nhập dữ liệu", f"Không nhập được dữ liệu từ file Excel.\n{e}", parent=self.root)
            self.status_var.set("Lỗi khi nhập dữ liệu!")

    # --- Change Master Password Feature ---
    def change_master_password(self):
         """Mở hộp thoại để đổi mật khẩu master."""
         # Kiểm tra xem ứng dụng có bị khóa không
         if self._is_locked:
             self.status_var.set("Ứng dụng đang bị khóa. Không thể đổi mật khẩu.")
             messagebox.showwarning("Ứng dụng bị khóa", "Vui lòng mở khóa ứng dụng trước khi đổi mật khẩu master.", parent=self.root)
             return

         # Hiển thị hộp thoại đổi mật khẩu
         dialog = ChangePasswordDialog(self.root, self.encryption_manager)
         self.root.wait_window(dialog) # Chờ hộp thoại đóng

         # Sau khi hộp thoại đóng, nếu đổi mật khẩu thành công, EncryptionManager đã được cập nhật.
         # Không cần làm gì thêm ở đây ngoài việc thông báo nếu dialog tự nó chưa làm.
         # (Hộp thoại ChangePasswordDialog đã hiển thị thông báo thành công/thất bại)


# --- Thực thi Chính ---
# --- Thực thi Chính ---
if __name__ == "__main__":
    # Create the Tkinter root window
    root = tk.Tk()

    # Set App ID (Windows) - Try placing it here, right after Tk() is created
    # This might help with taskbar icon issues on some systems,
    # but means the app ID is set even if authentication fails.
    # Decide if this is acceptable behavior.
    if os.name == 'nt':
        myappid = "YouTubeChannelManager.App.2.7" # Tăng version nếu có thay đổi đáng kể
        try:
            # Check if root window exists before calling after()
            if root.winfo_exists():
                 ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID(myappid)
                 print(f"Đã đặt AppUserModelID: {myappid}")
        except Exception as e:
             print(f"Cảnh báo: Không thể đặt AppUserModelID - {e}")
    # Initialize the Encryption Manager
    # This also handles loading or creating the salt file
    encryption_manager = EncryptionManager()

    # If the salt could not be loaded or created, exit the application
    if encryption_manager._salt is None:
        # The messagebox should have been shown in _load_or_create_salt
        # Ensure root is destroyed if salt loading failed
        if root and root.winfo_exists():
             root.destroy()
        exit()


    # Initialize the main application class
    # This class handles the master password verification and building the main UI
    # Note: The initial window size is set in __init__, but centering on screen is called after verification is complete.
    # Passing encryption_manager instance
    app = YouTubeChannelManager(root, encryption_manager)


    # Check if authentication was successful and the root window still exists
    # (it might have been destroyed if authentication was cancelled or failed repeatedly)
    # If authentication failed or was cancelled, the application should have already exited via root.destroy() or root.quit()
    # The check `if hasattr(app, 'master_password_verified') and app.master_password_verified and root.winfo_exists():` is already in the original code
    # to control whether mainloop starts. We can keep it like that.
    if hasattr(app, 'master_password_verified') and app.master_password_verified  and root and root.winfo_exists():
        # Start the Tkinter event loop if everything is initialized correctly
        root.mainloop()
    else:
              print("Application initialization failed or root window destroyed. Exiting.")



