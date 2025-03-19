#!/usr/bin/env python3
"""
Tulsa Meeting Agendas Scraper

A tool for downloading meeting agendas from the City of Tulsa website using Selenium
to interact with JavaScript-loaded content.
"""
import os
import time
import argparse
import logging
import re
import datetime
from urllib.parse import urljoin
import requests
from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.common.action_chains import ActionChains
from selenium.webdriver.common.keys import Keys
from webdriver_manager.chrome import ChromeDriverManager
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.common.exceptions import TimeoutException, NoSuchElementException, ElementClickInterceptedException

# Set up logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.StreamHandler()
    ]
)

class TulsaMeetingScraper:
    """Class to scrape meeting agendas from the City of Tulsa website"""
    
    def __init__(self, output_dir="downloaded_agendas", headless=True, 
                 start_date=None, end_date=None, board_filter=None):
        """
        Initialize the scraper
        
        Args:
            output_dir (str): Directory to save downloaded PDFs
            headless (bool): Run browser in headless mode
            start_date (str): Start date for filtering meetings (format: MM/DD/YYYY)
            end_date (str): End date for filtering meetings (format: MM/DD/YYYY)
            board_filter (str): Filter for specific board names (case-insensitive substring match)
        """
        self.output_dir = output_dir
        self.url = "https://www.cityoftulsa.org/government/meeting-agendas/"
        
        # Parse date filters if provided
        self.start_date = self._parse_date(start_date) if start_date else None
        self.end_date = self._parse_date(end_date) if end_date else None
        self.board_filter = board_filter.lower() if board_filter else None
        
        # Create output directory if it doesn't exist
        if not os.path.exists(output_dir):
            os.makedirs(output_dir)
        
        # Set up Chrome options
        chrome_options = Options()
        if headless:
            chrome_options.add_argument("--headless=new")
        chrome_options.add_argument("--window-size=1920,1080")
        chrome_options.add_argument("--disable-notifications")
        chrome_options.add_argument("--disable-gpu")
        chrome_options.add_argument("--no-sandbox")
        chrome_options.add_argument("--disable-dev-shm-usage")
        
        # Initialize the WebDriver with webdriver-manager
        self.driver = webdriver.Chrome(
            service=Service(ChromeDriverManager().install()),
            options=chrome_options
        )
        self.wait = WebDriverWait(self.driver, 10)
    
    def _parse_date(self, date_str):
        """
        Parse date string to datetime object
        
        Args:
            date_str (str): Date string in format MM/DD/YYYY
            
        Returns:
            datetime.datetime: Parsed date
        """
        try:
            return datetime.datetime.strptime(date_str, "%m/%d/%Y")
        except ValueError:
            logging.error(f"Invalid date format: {date_str}. Expected format: MM/DD/YYYY")
            return None
    
    def __del__(self):
        """Clean up resources"""
        if hasattr(self, 'driver'):
            self.driver.quit()
    
    def navigate_to_agenda_page(self):
        """Navigate to the meeting agendas page"""
        logging.info(f"Navigating to {self.url}")
        self.driver.get(self.url)
        # Wait for the page to load - look for the tab content element
        try:
            self.wait.until(EC.presence_of_element_located((By.CLASS_NAME, "tab-content")))
            # Additional wait to ensure JavaScript has run
            time.sleep(2)
            
            # Maximize window to minimize interference from dropdown menus
            self.driver.maximize_window()
            
            # Scroll down to the tab content area to avoid dropdown menus
            tab_content = self.driver.find_element(By.CLASS_NAME, "tab-content")
            self.driver.execute_script("arguments[0].scrollIntoView(true);", tab_content)
            time.sleep(1)
            
        except TimeoutException:
            logging.error("Timed out waiting for page to load. Check if the website structure has changed.")
            raise
    
    def _safe_click(self, element, max_retries=3):
        """
        Try to safely click an element, handling possible interceptions
        
        Args:
            element: The WebElement to click
            max_retries: Maximum number of retry attempts
            
        Returns:
            bool: True if successful, False otherwise
        """
        retries = 0
        while retries < max_retries:
            try:
                # Try multiple click strategies
                try:
                    # Scroll to element with offset to avoid dropdown menus
                    self.driver.execute_script("arguments[0].scrollIntoView({block: 'center'});", element)
                    time.sleep(0.5)
                    
                    # Try standard click
                    element.click()
                    return True
                except ElementClickInterceptedException:
                    # Try JavaScript click
                    self.driver.execute_script("arguments[0].click();", element)
                    return True
            except Exception as e:
                logging.warning(f"Click attempt {retries+1} failed: {e}")
                retries += 1
                time.sleep(0.5)
        
        logging.error(f"Failed to click element after {max_retries} attempts")
        return False
    
    def expand_all_boards(self):
        """Click on each board name to expand the hidden tables"""
        # Find all board elements by the board name divs
        board_elements = self.driver.find_elements(By.XPATH, "//div[@id='boardName' and @class='expandCollapse']")
        
        # Filter boards if board_filter is specified
        if self.board_filter:
            filtered_boards = [board for board in board_elements 
                              if self.board_filter.lower() in board.text.strip().lower()]
            board_elements = filtered_boards
            logging.info(f"Filtered to {len(board_elements)} boards matching '{self.board_filter}'")
        
        num_boards = len(board_elements)
        logging.info(f"Found {num_boards} boards to expand")
        
        for i, board in enumerate(board_elements, 1):
            board_name = board.text.strip()
            logging.info(f"Expanding board {i}/{num_boards}: {board_name}")
            
            # Try to safely click on the board name
            self._safe_click(board)
            time.sleep(0.5)  # Wait for table to load
    
    def _is_date_in_range(self, date_str):
        """
        Check if a date is within the specified range
        
        Args:
            date_str (str): Date string from the webpage
            
        Returns:
            bool: True if date is in range or no range specified, False otherwise
        """
        # If no date filters specified, return True
        if not self.start_date and not self.end_date:
            return True
            
        try:
            # Try multiple date formats
            date_formats = ["%m/%d/%Y", "%m/%d/%y"]
            meeting_date = None
            
            for date_format in date_formats:
                try:
                    meeting_date = datetime.datetime.strptime(date_str, date_format)
                    break
                except ValueError:
                    continue
            
            if not meeting_date:
                logging.warning(f"Could not parse date: {date_str}")
                return False
                
            # Check start date
            if self.start_date and meeting_date < self.start_date:
                return False
                
            # Check end date
            if self.end_date and meeting_date > self.end_date:
                return False
                
            return True
        except Exception as e:
            logging.error(f"Error checking date range for {date_str}: {e}")
            return False
    
    def extract_meeting_data(self):
        """Extract meeting information from the expanded tables"""
        # Find all board name elements
        board_elements = self.driver.find_elements(By.XPATH, "//div[@id='boardName' and @class='expandCollapse']")
        all_meetings = []
        
        # Filter boards if board_filter is specified
        if self.board_filter:
            filtered_boards = [board for board in board_elements 
                              if self.board_filter.lower() in board.text.strip().lower()]
            board_elements = filtered_boards
        
        for board in board_elements:
            board_name = board.text.strip()
            logging.info(f"Extracting data for board: {board_name}")
            
            # Find the associated table
            try:
                # Get the parent div (boardRow)
                parent_div = board.find_element(By.XPATH, "./..")
                
                # Find the table within the parent div
                try:
                    table = parent_div.find_element(By.TAG_NAME, "table")
                    
                    # Check if table is still hidden (class contains "hidden")
                    if "hidden" in table.get_attribute("class"):
                        logging.warning(f"Table for {board_name} is still hidden. Trying to expand it.")
                        
                        # Try clicking the plus icon if available
                        try:
                            plus_icon = parent_div.find_element(By.XPATH, ".//div[@id='plus' and contains(@class, 'glyphicon-plus')]")
                            self._safe_click(plus_icon)
                        except:
                            # If plus icon not found, try clicking the board name
                            self._safe_click(board)
                        
                        time.sleep(1)  # Wait for table to become visible
                        
                        # Retry finding the table with updated class
                        table = parent_div.find_element(By.TAG_NAME, "table")
                
                    # Get tbody element to extract rows
                    tbody_element = table.find_element(By.TAG_NAME, "tbody")
                    tbody_id = tbody_element.get_attribute("id")
                    
                    # Directly find rows in the current tbody
                    rows = tbody_element.find_elements(By.TAG_NAME, "tr")
                    
                    if not rows:
                        logging.warning(f"No meeting data found for board: {board_name}")
                        continue
                    
                    for row in rows:
                        cells = row.find_elements(By.TAG_NAME, "td")
                        
                        if len(cells) >= 3:
                            try:
                                # Extract date cell that contains the link
                                date_cell = cells[0]
                                try:
                                    link_element = date_cell.find_element(By.TAG_NAME, "a")
                                    date = link_element.text.strip()
                                    pdf_url = link_element.get_attribute("href")
                                except NoSuchElementException:
                                    logging.warning(f"No link found in date cell for {board_name}. Skipping row.")
                                    continue
                                
                                # Skip if date is not in range
                                if not self._is_date_in_range(date):
                                    logging.debug(f"Skipping meeting {date} - not in date range")
                                    continue
                                
                                # Extract time and meeting type
                                time_text = cells[1].text.strip() if cells[1].text.strip() else "No Time"
                                meeting_type = cells[2].text.strip()
                                
                                meeting_data = {
                                    "board": board_name,
                                    "date": date,
                                    "time": time_text,
                                    "type": meeting_type,
                                    "url": pdf_url
                                }
                                
                                all_meetings.append(meeting_data)
                            except Exception as e:
                                logging.error(f"Error processing row for board {board_name}: {e}")
                                continue
                
                except NoSuchElementException:
                    logging.warning(f"No table found for board: {board_name}")
            except Exception as e:
                logging.error(f"Error extracting data for board {board_name}: {e}")
        
        logging.info(f"Extracted data for {len(all_meetings)} meetings")
        return all_meetings
    
    def download_pdfs(self, meetings):
        """
        Download PDF files for meetings
        
        Args:
            meetings (list): List of meeting data dictionaries
        """
        download_count = 0
        
        for i, meeting in enumerate(meetings, 1):
            board_name = meeting["board"]
            date = meeting["date"]
            time_text = meeting["time"]
            meeting_type = meeting["type"]
            pdf_url = meeting["url"]
            
            # Create directory for board if it doesn't exist
            board_dir = os.path.join(self.output_dir, self._sanitize_filename(board_name))
            if not os.path.exists(board_dir):
                os.makedirs(board_dir)
            
            # Create sanitized date for filename
            date_parts = re.findall(r'\d+', date)
            if len(date_parts) >= 3:
                date_str = f"{date_parts[0]}-{date_parts[1]}-{date_parts[2]}"
            else:
                date_str = self._sanitize_filename(date)
            
            # Determine filename
            if time_text == "No Time":
                filename = f"{date_str}_{self._sanitize_filename(meeting_type)}_meeting_schedule.pdf"
            else:
                filename = f"{date_str}_{self._sanitize_filename(time_text)}_{self._sanitize_filename(meeting_type)}.pdf"
            
            output_path = os.path.join(board_dir, filename)
            
            # Check if file already exists
            if os.path.exists(output_path):
                logging.info(f"File already exists, skipping: {output_path}")
                continue
            
            logging.info(f"Downloading {i}/{len(meetings)}: {board_name} - {date} - {meeting_type}")
            
            try:
                # Download the PDF using requests
                response = requests.get(pdf_url, timeout=30)
                response.raise_for_status()
                
                # Save to file
                with open(output_path, 'wb') as file:
                    file.write(response.content)
                
                logging.info(f"Successfully downloaded: {output_path}")
                download_count += 1
                
                # Add a small delay between downloads
                time.sleep(0.5)
            except requests.exceptions.RequestException as e:
                logging.error(f"Error downloading PDF from {pdf_url}: {e}")
            except Exception as e:
                logging.error(f"Error saving file {output_path}: {e}")
        
        logging.info(f"Downloaded {download_count} PDFs out of {len(meetings)} meetings")
        return download_count
    
    def _sanitize_filename(self, name):
        """
        Sanitize a string to be used as a filename
        
        Args:
            name (str): String to sanitize
            
        Returns:
            str: Sanitized string
        """
        if not name:
            return "unknown"
            
        # Replace invalid characters with underscores
        sanitized = re.sub(r'[\\/*?:"<>|]', "_", name)
        # Replace multiple spaces with a single underscore
        sanitized = re.sub(r'\s+', "_", sanitized)
        return sanitized
    
    def run(self):
        """Run the scraper"""
        try:
            # Navigate to the agenda page
            self.navigate_to_agenda_page()
            
            # Expand all boards
            self.expand_all_boards()
            
            # Extract meeting data
            meetings = self.extract_meeting_data()
            
            if meetings:
                # Download PDFs
                download_count = self.download_pdfs(meetings)
                return download_count
            else:
                logging.warning("No meeting data found. Check if the website structure has changed.")
                return 0
        finally:
            # Clean up
            self.driver.quit()

def main():
    """Main entry point for the script"""
    parser = argparse.ArgumentParser(
        description='Download meeting agendas from the City of Tulsa website',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
        Examples:
        # Download all meeting agendas
        python tulsa_meeting_scraper.py
        
        # Save files to a custom directory
        python tulsa_meeting_scraper.py --output my_agendas
        
        # Run with visible browser
        python tulsa_meeting_scraper.py --visible
        
        # Download agendas for a specific date range
        python tulsa_meeting_scraper.py --start-date 01/01/2023 --end-date 12/31/2023
        
        # Download agendas for a specific board
        python tulsa_meeting_scraper.py --board "City Council"
        """
    )
    
    parser.add_argument('--output', default='downloaded_agendas',
                        help='Directory to save downloaded PDFs (default: %(default)s)')
    parser.add_argument('--visible', action='store_true',
                        help='Run with visible browser (default: headless)')
    parser.add_argument('--start-date',
                        help='Start date for filtering meetings (format: MM/DD/YYYY)')
    parser.add_argument('--end-date',
                        help='End date for filtering meetings (format: MM/DD/YYYY)')
    parser.add_argument('--board',
                        help='Filter for specific board names (case-insensitive substring match)')
    
    args = parser.parse_args()
    
    logging.info("Starting Tulsa Meeting Agendas scraper")
    
    # Log date range if specified
    if args.start_date or args.end_date:
        date_range = []
        if args.start_date:
            date_range.append(f"start: {args.start_date}")
        if args.end_date:
            date_range.append(f"end: {args.end_date}")
        logging.info(f"Date filtering: {', '.join(date_range)}")
    
    # Log board filter if specified
    if args.board:
        logging.info(f"Board filter: '{args.board}'")
    
    scraper = TulsaMeetingScraper(
        output_dir=args.output,
        headless=not args.visible,
        start_date=args.start_date,
        end_date=args.end_date,
        board_filter=args.board
    )
    
    download_count = scraper.run()
    logging.info(f"Scraper completed. Downloaded {download_count} PDFs.")

if __name__ == "__main__":
    main() 