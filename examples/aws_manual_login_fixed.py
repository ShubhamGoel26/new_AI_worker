import asyncio
import json
import logging
import os
import sys
from datetime import datetime

from dotenv import load_dotenv
from langchain_openai import ChatOpenAI
from mss import mss
from playwright.async_api import async_playwright

from browser_use import Agent

# Adjust sys.path to include project root
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

# Load environment variables (if needed for other settings)
load_dotenv()

# Create directories for screenshots and debug logs
screenshot_dir = 'screenshots'
debug_log_dir = 'debug_logs'
os.makedirs(screenshot_dir, exist_ok=True)
os.makedirs(debug_log_dir, exist_ok=True)

# LLM config
llm = ChatOpenAI(
	model='gpt-4o',
	temperature=0.0,
)


class ScreenshotHandler(logging.Handler):
	def __init__(self, log_file, screenshot_dir):
		super().__init__()
		self.log_file = log_file
		self.screenshot_dir = screenshot_dir
		self.step = 1
		self.last_goal = ''
		self.debug_file = os.path.join(debug_log_dir, 'debug_log.txt')

	async def capture_screenshot(self, filename):
		# Increase delay to ensure page loads
		await asyncio.sleep(3)
		with mss() as sct:
			# Focus on browser region (adjust coordinates as needed)
			monitor = {'top': 100, 'left': 100, 'width': 1200, 'height': 800}
			sct.shot(mon=monitor, output=filename)

	def emit(self, record):
		message = record.getMessage()
		with open(self.debug_file, 'a', encoding='utf-8') as f:
			f.write(f"DEBUG: Checking message: '{message}'\n")
		triggers = [
			'Action 1/1:',
			'Next goal:',
			'Searched for',
			'Navigating to',
			'Entering',
			'Clicking',
			'User logged in',
			'Clicked',
		]
		if any(trigger in message for trigger in triggers):
			timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
			filename = f'{self.screenshot_dir}/step_{self.step}_{timestamp}.png'
			try:
				# Schedule the async screenshot capture
				asyncio.create_task(self.capture_screenshot(filename))
				log_entry = {
					'step': self.step,
					'action': message
					if any(
						t in message
						for t in ['Action', 'Navigating', 'Entering', 'Clicking', 'Searched for', 'User logged in', 'Clicked']
					)
					else '',
					'next_goal': message if 'Next goal' in message else self.last_goal,
					'screenshot': filename,
				}
				with open(self.log_file, 'a', encoding='utf-8') as f:
					json.dump(log_entry, f)
					f.write('\n')
				print(f'Step {self.step}: Saved {filename}')
				if 'Next goal:' in message:
					self.last_goal = message
				self.step += 1
			except Exception as e:
				print(f'Failed to save screenshot: {e}')


async def main():
	# Set up logging handler
	log_file = f'{screenshot_dir}/log.json'
	handler = ScreenshotHandler(log_file, screenshot_dir)
	handler.setLevel(logging.INFO)
	logging.getLogger('').addHandler(handler)
	logging.getLogger('browser_use').addHandler(handler)
	logging.getLogger('agent').addHandler(handler)
	logging.getLogger('controller').addHandler(handler)

	# Initialize Playwright browser
	async with async_playwright() as p:
		browser = await p.chromium.launch(headless=False)  # Visible for manual login
		context = await browser.new_context()
		page = await context.new_page()

		try:
			# Step 1: Open browser and let user log in manually
			print('Opening AWS login page...')
			await page.goto('https://console.aws.amazon.com/')
			logging.info('Navigating to https://console.aws.amazon.com/')
			print('\nPlease log into your AWS account manually in the browser.')
			input('Press Enter after you have successfully logged in and are on the AWS console dashboard: ')
			logging.info('User logged in to AWS console')

			# Create a new Agent instance to clear memory
			agent = Agent(task='', llm=llm)

			# Step 2: Loop for user actions
			while True:
				# Step 3: Ask user for next action
				action = input(
					"\nEnter the next action to perform in AWS (e.g., 'List S3 buckets') or type 'exit' to quit: "
				).strip()
				if action.lower() == 'exit':
					print('Exiting...')
					break

				# Step 4: Perform action, capture screenshot and log
				print(f'Performing action: {action}')
				agent.task = f'In the AWS console, {action}'
				logging.info(f'Set task: {agent.task}')
				await agent.run()

		finally:
			# Clean up
			logging.getLogger('').removeHandler(handler)
			logging.getLogger('browser_use').removeHandler(handler)
			logging.getLogger('agent').removeHandler(handler)
			logging.getLogger('controller').removeHandler(handler)
			await context.close()
			await browser.close()


if __name__ == '__main__':
	asyncio.run(main())
