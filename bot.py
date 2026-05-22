# =============================================================================
# BOT PLAYWRIGHT - HỆ THỐNG TỰ ĐỘNG HÓA GIÁM SÁT WEB
# =============================================================================
# Mô tả: Bot theo dõi phiên live trên web nội bộ, gửi tín hiệu qua Telegram
# Deploy: Railway (chạy 24/7)
# =============================================================================

import asyncio
import random
import os
from datetime import datetime
from playwright.async_api import async_playwright, TimeoutError as PlaywrightTimeoutError
import httpx

# =============================================================================
# MODULE 1: CONFIG - CẤU HÌNH TOÀN BỘ HỆ THỐNG
# =============================================================================
# ⚠️  CHỈNH SỬA PHẦN NÀY KHI CẦN THAY ĐỔI SELECTORS HOẶC NHÃN
# =============================================================================

class Config:
    # --- URL trang web cần giám sát ---
    # TODO: Thay bằng URL thật của trang web nội bộ
    TARGET_URL = os.getenv("TARGET_URL", "https://example.com/live")

    # --- Telegram ---
    TELEGRAM_TOKEN = os.getenv("TELEGRAM_TOKEN", "YOUR_BOT_TOKEN_HERE")
    TELEGRAM_CHAT_ID = os.getenv("TELEGRAM_CHAT_ID", "YOUR_CHAT_ID_HERE")

    # --- CSS Selectors (chỉnh tại đây khi web thay đổi giao diện) ---
    # Selector cho phần tử đếm ngược (countdown timer)
    # Ví dụ: "#countdown", ".timer", "[data-countdown]"
    CSS_COUNTDOWN = os.getenv("CSS_COUNTDOWN", "#countdown")

    # Selector nhận biết phiên live đang bắt đầu
    # Ví dụ: ".live-badge", ".session-active", "[data-status='live']"
    CSS_LIVE_INDICATOR = os.getenv("CSS_LIVE_INDICATOR", ".live-badge")

    # Selector đọc kết quả phiên (hiển thị sau khi phiên kết thúc)
    # Ví dụ: ".result-label", "#session-result", ".outcome-text"
    CSS_RESULT = os.getenv("CSS_RESULT", ".result-label")

    # Selector khu vực chứa thông tin phiên (dùng để kiểm tra trạng thái)
    CSS_SESSION_AREA = os.getenv("CSS_SESSION_AREA", ".session-area")

    # --- Nhãn tín hiệu giao dịch ---
    # Thay đổi tại đây nếu muốn dùng nhãn khác
    LABEL_LENH_A = "Lệnh A"   # Tín hiệu lệnh thứ nhất (ví dụ: BUY, UP, CALL)
    LABEL_LENH_B = "Lệnh B"   # Tín hiệu lệnh thứ hai (ví dụ: SELL, DOWN, PUT)

    # --- Nhãn kết quả từ web ---
    # Thay bằng text thật hiển thị trên web khi thắng/thua
    # Ví dụ: "WIN", "LOSE", "Thắng", "Thua", "UP", "DOWN"
    LABEL_DUNG_WEB = os.getenv("LABEL_DUNG_WEB", "WIN")   # Text web khi kết quả đúng (thắng)
    LABEL_SAI_WEB  = os.getenv("LABEL_SAI_WEB",  "LOSE")  # Text web khi kết quả sai (thua)

    # --- Nhãn hiển thị trong Telegram ---
    LABEL_DUNG = "Đúng"   # Hiển thị khi thắng
    LABEL_SAI  = "Sai"    # Hiển thị khi thua

    # --- Tham số giao dịch ---
    PERCENT_LENH = 5   # % mỗi lệnh (không đổi)

    # --- Ngưỡng Session Manager ---
    CHOT_LAI_MIN  = 10   # % lãi tối thiểu để chốt mục tiêu
    CHOT_LAI_MAX  = 15   # % lãi tối đa để chốt mục tiêu
    WIN_STREAK    = 3    # Số lần thắng liên tiếp để chốt
    CAT_LO        = -15  # % lỗ để cắt lỗ (giá trị âm)

    # --- Thời gian ---
    WAIT_AFTER_LIVE_START = 2   # Giây chờ sau khi phiên live bắt đầu
    COUNTDOWN_THRESHOLD   = 5   # Giây còn lại trong đếm ngược để bắt đầu theo dõi
    RESULT_WAIT_TIMEOUT   = 30  # Giây chờ tối đa để đọc kết quả
    LOOP_INTERVAL         = 1   # Giây giữa mỗi vòng kiểm tra
    RECONNECT_WAIT        = 10  # Giây chờ trước khi kết nối lại khi lỗi

    # --- Playwright ---
    HEADLESS = True   # True = chạy ẩn (Railway), False = hiện browser (debug)
    SLOW_MO  = 0      # Milliseconds delay giữa các action (0 = không delay)


# =============================================================================
# MODULE 2: TELEGRAM - GỬI TIN NHẮN QUA TELEGRAM BOT
# =============================================================================

class TelegramModule:
    def __init__(self, token: str, chat_id: str):
        self.token = token
        self.chat_id = chat_id
        self.base_url = f"https://api.telegram.org/bot{token}"

    async def send_message(self, text: str) -> bool:
        """Gửi tin nhắn văn bản đến Telegram."""
        try:
            async with httpx.AsyncClient(timeout=10) as client:
                resp = await client.post(
                    f"{self.base_url}/sendMessage",
                    json={"chat_id": self.chat_id, "text": text, "parse_mode": "HTML"}
                )
                return resp.status_code == 200
        except Exception as e:
            print(f"[Telegram] Lỗi gửi tin: {e}")
            return False

    async def send_signal(self, lenh: str, percent: int) -> bool:
        """Gửi tín hiệu lệnh A hoặc lệnh B kèm tham số %."""
        now = datetime.now().strftime("%H:%M:%S")
        text = (
            f"🚀 <b>TÍN HIỆU MỚI</b>\n"
            f"⏰ {now}\n"
            f"📊 Lệnh: <b>{lenh}</b>\n"
            f"💰 Mức: <b>{percent}%</b>"
        )
        return await self.send_message(text)

    async def send_result(self, lenh: str, ket_qua: str, balance_change: float, session_balance: float) -> bool:
        """Gửi báo cáo kết quả Đúng/Sai."""
        now = datetime.now().strftime("%H:%M:%S")
        icon = "✅" if ket_qua == Config.LABEL_DUNG else "❌"
        change_str = f"+{balance_change:.1f}%" if balance_change > 0 else f"{balance_change:.1f}%"
        text = (
            f"{icon} <b>KẾT QUẢ</b>\n"
            f"⏰ {now}\n"
            f"📊 Lệnh: <b>{lenh}</b>\n"
            f"🎯 Kết quả: <b>{ket_qua}</b>\n"
            f"📈 Thay đổi: <b>{change_str}</b>\n"
            f"💼 Session: <b>{session_balance:+.1f}%</b>"
        )
        return await self.send_message(text)

    async def send_chot_muc_tieu(self, session_balance: float) -> bool:
        """Gửi thông báo chốt mục tiêu."""
        text = (
            f"🎉 <b>CHỐT MỤC TIÊU</b>\n"
            f"💰 Lãi phiên: <b>+{session_balance:.1f}%</b>\n"
            f"✅ Hoàn thành kế hoạch - Nghỉ ngơi!"
        )
        return await self.send_message(text)

    async def send_dung_ke_hoach(self, session_balance: float) -> bool:
        """Gửi thông báo dừng theo kế hoạch (cắt lỗ)."""
        text = (
            f"🛑 <b>DỪNG THEO KẾ HOẠCH</b>\n"
            f"📉 Lỗ phiên: <b>{session_balance:.1f}%</b>\n"
            f"⚠️ Đã chạm ngưỡng cắt lỗ - Bảo vệ vốn!"
        )
        return await self.send_message(text)

    async def send_stop(self, reason: str = "") -> bool:
        """Gửi thông báo bot đang dừng."""
        text = f"⏹️ <b>BOT DỪNG</b>\n📝 Lý do: {reason}" if reason else "⏹️ <b>BOT DỪNG</b>"
        return await self.send_message(text)

    async def send_start(self) -> bool:
        """Gửi thông báo bot đã khởi động."""
        text = (
            f"🤖 <b>BOT KHỞI ĐỘNG</b>\n"
            f"⏰ {datetime.now().strftime('%d/%m/%Y %H:%M:%S')}\n"
            f"🔄 Đang theo dõi phiên live..."
        )
        return await self.send_message(text)


# =============================================================================
# MODULE 3: SESSION MANAGER - QUẢN LÝ TRẠNG THÁI VÀ BALANCE
# =============================================================================

class SessionManager:
    def __init__(self):
        self.reset()

    def reset(self):
        """Reset session về trạng thái ban đầu."""
        self.session_balance = 0.0   # % lãi/lỗ tích lũy trong phiên
        self.win_streak      = 0     # Số lần thắng liên tiếp
        self.total_trades    = 0     # Tổng số lệnh trong phiên
        self.is_active       = True  # Phiên đang hoạt động

    def process_result(self, ket_qua: str):
        """
        Xử lý kết quả lệnh, cập nhật balance và win streak.
        Trả về: (balance_change, action)
        action: None | 'chot' | 'cat_lo'
        """
        self.total_trades += 1

        if ket_qua == Config.LABEL_DUNG:
            change = float(Config.PERCENT_LENH)
            self.session_balance += change
            self.win_streak += 1
        else:
            change = float(-Config.PERCENT_LENH)
            self.session_balance += change
            self.win_streak = 0

        print(f"[Session] Balance: {self.session_balance:+.1f}% | Streak: {self.win_streak} | Trades: {self.total_trades}")

        # Kiểm tra chốt mục tiêu
        if (Config.CHOT_LAI_MIN <= self.session_balance <= Config.CHOT_LAI_MAX) or \
           (self.win_streak >= Config.WIN_STREAK):
            self.is_active = False
            return change, "chot"

        # Kiểm tra cắt lỗ
        if self.session_balance <= Config.CAT_LO:
            self.is_active = False
            return change, "cat_lo"

        return change, None

    def pick_signal(self) -> str:
        """Chọn ngẫu nhiên Lệnh A hoặc Lệnh B."""
        return random.choice([Config.LABEL_LENH_A, Config.LABEL_LENH_B])


# =============================================================================
# MODULE 4: SCREENSHOT - PLACEHOLDER SẴN SÀNG
# =============================================================================

class ScreenshotModule:
    def __init__(self, page):
        self.page = page

    async def capture(self, filename: str = None) -> str:
        """
        Chụp ảnh màn hình hiện tại.
        TODO: Tích hợp với Telegram để gửi ảnh nếu cần.
        """
        try:
            if filename is None:
                filename = f"screenshot_{datetime.now().strftime('%Y%m%d_%H%M%S')}.png"
            await self.page.screenshot(path=filename)
            print(f"[Screenshot] Đã chụp: {filename}")
            return filename
        except Exception as e:
            print(f"[Screenshot] Lỗi: {e}")
            return None

    async def capture_element(self, selector: str, filename: str = None) -> str:
        """
        Chụp ảnh một phần tử cụ thể trên trang.
        TODO: Có thể dùng để chụp kết quả phiên.
        """
        try:
            if filename is None:
                filename = f"element_{datetime.now().strftime('%Y%m%d_%H%M%S')}.png"
            element = await self.page.query_selector(selector)
            if element:
                await element.screenshot(path=filename)
                print(f"[Screenshot] Đã chụp element: {filename}")
                return filename
            return None
        except Exception as e:
            print(f"[Screenshot] Lỗi chụp element: {e}")
            return None


# =============================================================================
# MODULE 5: PLAYWRIGHT MONITOR - THEO DÕI WEB VÀ NHẬN BIẾT PHIÊN LIVE
# =============================================================================

class PlaywrightMonitor:
    def __init__(self, telegram: TelegramModule, session_mgr: SessionManager):
        self.telegram    = telegram
        self.session_mgr = session_mgr
        self.browser     = None
        self.context     = None
        self.page        = None
        self.screenshot  = None
        self.last_seen_countdown = None
        self.in_live_session     = False
        self.current_signal      = None

    async def setup(self, playwright):
        """Khởi tạo browser và điều hướng đến trang web."""
        self.browser = await playwright.chromium.launch(
            headless=Config.HEADLESS,
            slow_mo=Config.SLOW_MO,
            args=["--no-sandbox", "--disable-setuid-sandbox", "--disable-dev-shm-usage"]
        )
        self.context = await self.browser.new_context(
            viewport={"width": 1280, "height": 800},
            user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"
        )
        self.page = await self.context.new_page()
        self.screenshot = ScreenshotModule(self.page)

        print(f"[Playwright] Đang mở: {Config.TARGET_URL}")
        await self.page.goto(Config.TARGET_URL, wait_until="domcontentloaded", timeout=30000)
        print("[Playwright] Đã tải trang thành công")

    async def get_countdown_value(self) -> int:
        """
        Đọc giá trị đếm ngược từ trang web.
        Trả về số giây còn lại, hoặc None nếu không tìm thấy.
        TODO: Điều chỉnh logic parse nếu format đếm ngược khác (MM:SS, v.v.)
        """
        try:
            element = await self.page.query_selector(Config.CSS_COUNTDOWN)
            if not element:
                return None
            text = await element.inner_text()
            text = text.strip()

            # Parse format "MM:SS" (ví dụ: "01:30" = 90 giây)
            if ":" in text:
                parts = text.split(":")
                if len(parts) == 2:
                    minutes = int(parts[0].strip())
                    seconds = int(parts[1].strip())
                    return minutes * 60 + seconds

            # Parse format số nguyên (ví dụ: "30")
            return int(text)

        except (ValueError, AttributeError):
            return None
        except Exception as e:
            print(f"[Playwright] Lỗi đọc countdown: {e}")
            return None

    async def is_live_session_active(self) -> bool:
        """
        Kiểm tra xem có phiên live đang hoạt động không.
        Dùng CSS_LIVE_INDICATOR để nhận biết.
        """
        try:
            element = await self.page.query_selector(Config.CSS_LIVE_INDICATOR)
            if not element:
                return False
            is_visible = await element.is_visible()
            return is_visible
        except Exception:
            return False

    async def read_result(self) -> str:
        """
        Đọc kết quả phiên từ trang web sau khi phiên kết thúc.
        Trả về Config.LABEL_DUNG hoặc Config.LABEL_SAI, hoặc None.
        TODO: Điều chỉnh logic map kết quả nếu web dùng text khác.
        """
        deadline = asyncio.get_event_loop().time() + Config.RESULT_WAIT_TIMEOUT
        while asyncio.get_event_loop().time() < deadline:
            try:
                element = await self.page.query_selector(Config.CSS_RESULT)
                if element and await element.is_visible():
                    text = (await element.inner_text()).strip().upper()
                    print(f"[Playwright] Đọc kết quả web: '{text}'")

                    if Config.LABEL_DUNG_WEB.upper() in text:
                        return Config.LABEL_DUNG
                    if Config.LABEL_SAI_WEB.upper() in text:
                        return Config.LABEL_SAI
            except Exception as e:
                print(f"[Playwright] Lỗi đọc kết quả: {e}")

            await asyncio.sleep(1)

        print("[Playwright] Timeout đọc kết quả - bỏ qua phiên này")
        return None

    async def wait_for_new_session(self):
        """
        Chờ phiên live mới bắt đầu.
        Phát hiện khi: countdown reset về giá trị cao hoặc live indicator xuất hiện.
        """
        print("[Playwright] Đang chờ phiên live mới...")
        prev_countdown = None

        while True:
            try:
                current = await self.get_countdown_value()
                live_active = await self.is_live_session_active()

                if current is not None and prev_countdown is not None:
                    # Phát hiện phiên mới: countdown tăng đột biến (reset)
                    if current > prev_countdown + 10:
                        print(f"[Playwright] Phát hiện phiên mới! Countdown reset: {prev_countdown}→{current}")
                        return

                # Hoặc live indicator vừa xuất hiện
                if live_active and not self.in_live_session:
                    print("[Playwright] Phát hiện phiên live mới qua indicator!")
                    return

                prev_countdown = current
            except Exception as e:
                print(f"[Playwright] Lỗi vòng chờ: {e}")

            await asyncio.sleep(Config.LOOP_INTERVAL)

    async def run_one_session(self):
        """Xử lý một phiên live: chờ → gửi tín hiệu → chờ kết quả → báo cáo."""
        # Chờ phiên mới
        await self.wait_for_new_session()
        self.in_live_session = True

        # Chờ 2 giây theo yêu cầu
        print(f"[Playwright] Chờ {Config.WAIT_AFTER_LIVE_START}s sau khi phiên bắt đầu...")
        await asyncio.sleep(Config.WAIT_AFTER_LIVE_START)

        # Kiểm tra session còn hoạt động không
        if not self.session_mgr.is_active:
            print("[Playwright] Session đã đóng, bỏ qua phiên này")
            self.in_live_session = False
            return

        # Chọn và gửi tín hiệu
        lenh = self.session_mgr.pick_signal()
        self.current_signal = lenh
        print(f"[Playwright] Gửi tín hiệu: {lenh} {Config.PERCENT_LENH}%")
        await self.telegram.send_signal(lenh, Config.PERCENT_LENH)

        # Chờ và đọc kết quả
        print("[Playwright] Chờ kết quả từ web...")
        ket_qua = await self.read_result()

        if ket_qua is None:
            print("[Playwright] Không đọc được kết quả, bỏ qua")
            self.in_live_session = False
            self.current_signal = None
            return

        # Xử lý kết quả qua Session Manager
        change, action = self.session_mgr.process_result(ket_qua)
        await self.telegram.send_result(lenh, ket_qua, change, self.session_mgr.session_balance)

        # Xử lý action chốt/cắt lỗ
        if action == "chot":
            await self.telegram.send_chot_muc_tieu(self.session_mgr.session_balance)
            print("[Session] Chốt mục tiêu! Reset session sau 60s...")
            await asyncio.sleep(60)
            self.session_mgr.reset()

        elif action == "cat_lo":
            await self.telegram.send_dung_ke_hoach(self.session_mgr.session_balance)
            print("[Session] Cắt lỗ! Reset session sau 60s...")
            await asyncio.sleep(60)
            self.session_mgr.reset()

        self.in_live_session = False
        self.current_signal = None

    async def close(self):
        """Đóng browser."""
        try:
            if self.context:
                await self.context.close()
            if self.browser:
                await self.browser.close()
        except Exception:
            pass


# =============================================================================
# MODULE 6: MAIN - ĐIỀU PHỐI TOÀN BỘ HỆ THỐNG (asyncio)
# =============================================================================

async def main():
    """Hàm chính: khởi động và chạy bot liên tục 24/7."""
    print("=" * 60)
    print("  BOT PLAYWRIGHT - KHỞI ĐỘNG")
    print(f"  {datetime.now().strftime('%d/%m/%Y %H:%M:%S')}")
    print("=" * 60)

    # Khởi tạo các module
    telegram = TelegramModule(Config.TELEGRAM_TOKEN, Config.TELEGRAM_CHAT_ID)
    session_mgr = SessionManager()

    # Gửi thông báo khởi động
    await telegram.send_start()

    # Vòng lặp chính - chạy liên tục 24/7
    while True:
        monitor = None
        try:
            async with async_playwright() as playwright:
                monitor = PlaywrightMonitor(telegram, session_mgr)
                await monitor.setup(playwright)
                print("[Main] Bot đang chạy, nhấn Ctrl+C để dừng")

                # Vòng lặp xử lý từng phiên
                while True:
                    await monitor.run_one_session()

        except KeyboardInterrupt:
            print("\n[Main] Nhận tín hiệu dừng từ người dùng")
            await telegram.send_stop("Người dùng dừng thủ công")
            break

        except PlaywrightTimeoutError as e:
            print(f"[Main] Timeout Playwright: {e}")
            print(f"[Main] Kết nối lại sau {Config.RECONNECT_WAIT}s...")
            await asyncio.sleep(Config.RECONNECT_WAIT)

        except Exception as e:
            print(f"[Main] Lỗi không xác định: {e}")
            print(f"[Main] Tự động kết nối lại sau {Config.RECONNECT_WAIT}s...")
            await asyncio.sleep(Config.RECONNECT_WAIT)

        finally:
            if monitor:
                await monitor.close()


if __name__ == "__main__":
    asyncio.run(main())
