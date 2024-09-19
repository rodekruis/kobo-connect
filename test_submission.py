from selenium import webdriver
from selenium.webdriver.firefox.options import Options
from selenium.webdriver.common.by import By
import time
import click
import random
import string


@click.command()
@click.option("--form", help="Kobo form ID")
@click.option("--url", help="Kobo form URL")
def test(form, url):
    options = Options()
    options.add_argument("-headless")
    driver = webdriver.Firefox(options=options)
    driver.get(url)
    time.sleep(5)

    questions = {
        "firstname": "".join(random.choices(string.ascii_uppercase, k=6)),
        "lastname": "".join(random.choices(string.ascii_uppercase, k=6)),
    }

    for question, answer in questions.items():
        text_input = driver.find_element(
            By.XPATH, f"//input[@name='/{form}/{question}']"
        )
        text_input.send_keys(answer)

    search_button = driver.find_element(By.ID, "submit-form")
    search_button.click()

    driver.close()


if __name__ == "__main__":
    test()
