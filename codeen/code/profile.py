import os
import re
import requests
from requests.adapters import HTTPAdapter, Retry
from bs4 import BeautifulSoup
from urllib.parse import urljoin, urlparse, parse_qs
import json

# Function to set up a requests session with retry logic
def create_session():
    session = requests.Session()
    retry_strategy = Retry(
        total=5,
        backoff_factor=1,
        status_forcelist=[500, 502, 503, 504],
        allowed_methods=["GET"]
    )
    adapter = HTTPAdapter(max_retries=retry_strategy)
    session.mount("http://", adapter)
    session.mount("https://", adapter)
    return session

# Function to extract information from a post
def extract_post_info(post_card, base_url):
    post_info = {}
    post_info['link'] = urljoin(base_url, post_card.find('a')['href'])
    post_info['title'] = post_card.find('header', class_='post-card__header').text.strip()

    attachments_div = post_card.find('div', string=lambda x: x and 'attachments' in x.lower())
    post_info['attachments'] = attachments_div.text.strip() if attachments_div else "No attachments"

    time_tag = post_card.find('time')
    post_info['date'] = time_tag['datetime'] if time_tag else "No date available"

    image_tag = post_card.find('img', class_='post-card__image')
    post_info['image'] = urljoin(base_url, image_tag['src']) if image_tag else "No image available"

    return post_info

# Function to extract the total number of posts
def get_total_posts(soup):
    total_posts_text = soup.find('small')
    if total_posts_text:
        total_posts = int(total_posts_text.text.strip().split(' of ')[1])
    else:
        total_posts = None
    return total_posts

# Function to sanitize filenames for filesystem compatibility
def sanitize_filename(filename):
    filename = re.sub(r'[<>:"/\\|?*]', '_', filename)
    return filename[:255]

# Function to ensure a unique filename in a directory
def ensure_unique_filename(path, filename):
    base, ext = os.path.splitext(filename)
    counter = 1
    new_filename = filename
    while os.path.exists(os.path.join(path, new_filename)):
        new_filename = f"{base}_duplicate{counter}{ext}"
        counter += 1
    return new_filename

# Function to get the filename from URL
def get_filename_from_url(url):
    query_params = parse_qs(urlparse(url).query)
    filename = query_params.get('f', [None])[0]
    if not filename:
        filename = os.path.basename(urlparse(url).path)
    return sanitize_filename(filename)

# Function to save posts to a text file
def save_posts_to_file(posts, filename="posts_info.txt"):
    with open(filename, 'w', encoding='utf-8') as f:
        for post in posts:
            f.write(f"Link: {post['link']}\n")
            f.write(f"Title: {post['title']}\n")
            f.write(f"Number of attachments: {post['attachments']}\n")
            f.write(f"Post date: {post['date']}\n")
            f.write(f"Cover image: {post['image']}\n")
            f.write("\n" + "-"*40 + "\n\n")

# Function to save post information to a text file named after the post title
def save_post_info(soup, folder):
    title_tag = soup.find("h1", class_="post__title")
    if title_tag:
        title = " ".join([span.text for span in title_tag.find_all("span")])
        title = sanitize_filename(title)
    else:
        title = "Untitled"

    info_file_path = os.path.join(folder, f"{title}.html")
    with open(info_file_path, "w", encoding="utf-8") as f:
        # Write the initial HTML structure
        f.write("<!DOCTYPE html>\n")
        f.write("<html lang=\"en\">\n")
        f.write("<head>\n")
        f.write("    <meta charset=\"UTF-8\">\n")
        f.write("    <meta name=\"viewport\" content=\"width=device-width, initial-scale=1.0\">\n")
        f.write(f"    <title>{title}</title>\n")
        f.write("</head>\n")
        f.write("<body>\n")

        # Write publication date
        published_tag = soup.find("div", class_="post__published")
        if published_tag:
            published_date = published_tag.text.strip().split(": ")[1]
            f.write(f"<p><strong>Publication date:</strong> {published_date}</p>\n")

        # Write import date
        imported_tag = soup.find("div", class_="post__added")
        if imported_tag and ": " in imported_tag.text:
            imported_date = imported_tag.text.strip().split(": ")[1]
            f.write(f"<p><strong>Import date:</strong> {imported_date}</p>\n")

        # Write tags
        tags_section = soup.find("section", id="post-tags")
        if tags_section:
            tags = [a.text for a in tags_section.find_all("a")]
            f.write(f"<p><strong>Tags:</strong> {', '.join(tags)}</p>\n")

        # Write attachments
        attachment_tags = soup.find_all("a", class_="post__attachment-link")
        if attachment_tags:
            f.write("<p><strong>Attachments:</strong></p>\n")
            f.write("<ul>\n")
            for attachment_tag in attachment_tags:
                attachment_url = attachment_tag["href"]
                attachment_name = attachment_tag.text.strip().split(" ")[-1]
                f.write(f"    <li>{attachment_name}: <a href=\"{attachment_url}\">{attachment_url}</a></li>\n")
                browse_tag = attachment_tag.find_next("a", href=True, string="browse »")
                if browse_tag:
                    browse_url = urlparse(url)._replace(path=browse_tag["href"]).geturl()
                    f.write(f"    <li>Attachment content: <a href=\"{browse_url}\">{browse_url}</a></li>\n")
            f.write("</ul>\n")

        # Write post content (entire HTML of post__content)
        content_div = soup.find("div", class_="post__content")
        if content_div:
            f.write("<div class=\"post__content\">\n")
            f.write(content_div.prettify())
            f.write("</div>\n")

        # Write comments
        comments_section = soup.find("footer", class_="post__footer")
        if comments_section:
            comments = comments_section.find_all("article", class_="comment")
            if comments:
                f.write("<p><strong>Comments:</strong></p>\n")
                f.write("<ul>\n")
                for comment in comments:
                    comment_author = comment.find("a", class_="comment__name").text.strip()
                    comment_text = comment.find("p", class_="comment__message").text.strip()
                    comment_date = comment.find("time", class_="timestamp")["datetime"]
                    f.write(f"    <li>{comment_author} ({comment_date}): {comment_text}</li>\n")
                f.write("</ul>\n")

        # Close HTML structure
        f.write("</body>\n")
        f.write("</html>\n")

# Function to download content from a URL
def download_content(url, config):
    session = create_session()
    headers = {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36'
    }
    try:
        response = session.get(url, headers=headers, timeout=60)
        response.raise_for_status()
        html_content = response.text
        soup = BeautifulSoup(html_content, "html.parser")

        parsed_url = urlparse(url)
        base_folder = "Kemono" if "kemono.su" in parsed_url.netloc or "kemono.party" in parsed_url.netloc else "Coomer"

        author_tag = soup.find("a", class_="post__user-name")
        if author_tag:
            author_name = author_tag.text.strip()
        else:
            meta_tag = soup.find("meta", property="og:image")
            if meta_tag:
                author_name = meta_tag["content"].split("/")[-1].split("-")[0]
            else:
                author_name = "UnknownAuthor"

        platform_name = urlparse(soup.find("meta", property="og:image")["content"]).path.split("/")[2] if soup.find("meta", property="og:image") else "UnknownPlatform"
        author_folder = f"{author_name}-{platform_name}"

        post_id = soup.find("meta", attrs={"name": "id"})["content"]
        post_folder = post_id
        post_path = os.path.join(base_folder, author_folder, "posts", post_folder)

        # Check if the post folder already exists
        if os.path.exists(post_path):
            print(f"Folder already exists, skipping download: {post_path}")
            return  # Skip processing if folder exists

        # If folder does not exist, create it
        os.makedirs(post_path)

        if config["save_info_txt"]:
            save_post_info(soup, post_path)

        downloaded_links = set()
        image_tags = soup.find_all("a", class_="fileThumb")

        for img_tag in image_tags:
            image_url = img_tag["href"]
            filename = get_filename_from_url(image_url)
            filename = ensure_unique_filename(post_path, filename)
            file_path = os.path.join(post_path, filename)

            if not os.path.exists(file_path):
                try:
                    image_response = session.get(image_url, timeout=60)
                    image_response.raise_for_status()
                    with open(file_path, "wb") as f:
                        f.write(image_response.content)
                    downloaded_links.add(image_url)
                except requests.exceptions.RequestException as e:
                    print(f"Failed to download image {image_url}: {e}")

        if config["download_attachments"]:
            attachment_tags = soup.find_all("a", class_="post__attachment-link")
            for attachment_tag in attachment_tags:
                attachment_url = attachment_tag["href"]
                filename = get_filename_from_url(attachment_url)
                filename = ensure_unique_filename(post_path, filename)
                file_path = os.path.join(post_path, filename)

                if not os.path.exists(file_path):
                    try:
                        attachment_response = session.get(attachment_url, timeout=60)
                        attachment_response.raise_for_status()
                        with open(file_path, "wb") as f:
                            f.write(attachment_response.content)
                        downloaded_links.add(attachment_url)
                    except requests.exceptions.RequestException as e:
                        print(f"Failed to download attachment {attachment_url}: {e}")

        if config["download_videos"]:
            video_tags = soup.find_all("a", class_="post__attachment-link")
            for video_tag in video_tags:
                video_url = video_tag["href"]
                filename = get_filename_from_url(video_url)
                filename = ensure_unique_filename(post_path, filename)
                file_path = os.path.join(post_path, filename)

                if not os.path.exists(file_path):
                    try:
                        video_response = session.get(video_url, timeout=60)
                        video_response.raise_for_status()
                        with open(file_path, "wb") as f:
                            f.write(video_response.content)
                        downloaded_links.add(video_url)
                    except requests.exceptions.RequestException as e:
                        print(f"Failed to download video {video_url}: {e}")

        print(f"Post content from {url} successfully downloaded!")
    except requests.exceptions.ChunkedEncodingError as e:
        print(f"ChunkedEncodingError occurred: {e}")
    except requests.exceptions.RequestException as e:
        print(f"RequestException occurred: {e}")

# Load settings from the JSON file
with open("code/profileconfig.json", "r") as f:
    config = json.load(f)

# Provided base URL
base_url = input("Please enter the Profile URL: ")

# Variable to store all posts
all_posts = []

# Iterate over pages to collect all posts
session = create_session()
page_number = 0
while True:
    url = f"{base_url}?o={page_number * 50}"
    try:
        response = session.get(url, headers={'User-Agent': 'Mozilla/5.0'}, timeout=60)
        response.raise_for_status()
        soup = BeautifulSoup(response.text, 'html.parser')

        if page_number == 0:
            total_posts = get_total_posts(soup)
            if total_posts:
                total_pages = (total_posts + 49) // 50
            else:
                total_pages = 1

        post_cards = soup.find_all('article', class_='post-card post-card--preview')
        if not post_cards:
            break

        for post_card in post_cards:
            post_info = extract_post_info(post_card, base_url)
            all_posts.append(post_info)

        if page_number >= total_pages - 1:
            break

        page_number += 1
    except requests.exceptions.RequestException as e:
        print(f"Failed to retrieve page {page_number}: {e}")
        break

# Filter posts based on profileconfig.json settings
filtered_posts = []
for post in all_posts:
    has_media = post['image'] != "No image available" or post['attachments'] != "No attachments"

    if config['both']:
        filtered_posts.append(post)
    elif config['files_only'] and has_media:
        filtered_posts.append(post)
    elif config['no_files'] and not has_media:
        filtered_posts.append(post)

# Save information of filtered posts to a text file
save_posts_to_file(filtered_posts)

# Iterate over all links of filtered posts and download content
for post in filtered_posts:
    download_content(post['link'], config)

print(f"Information from {len(filtered_posts)} posts saved and content downloaded successfully!")
