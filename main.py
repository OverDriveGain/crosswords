from alive_progress import alive_bar
import datetime, requests, re, shutil, PIL, os
from pdf2image import convert_from_path
LAST_DAY_FILE = 'last-date.txt'
DATE_FORMAT = '%Y/%m/%d'
os.environ["PATH"] = os.environ["PATH"] + ";./bin"
def clean(pdf_list):
    for i in pdf_list:
        os.remove(i[0])

PRINT_DIR = 'print'
def create_print_dir(date):
    try:
        out_dir = PRINT_DIR + '-' + date
        os.makedirs(out_dir)
    except FileExistsError:
        # directory already exists
        pass
    return out_dir

def read_last_day():
    date = datetime.datetime.today()
    date = date.strftime(DATE_FORMAT)
    with open(LAST_DAY_FILE, 'r') as outfile:
        date = outfile.read()
    return date

def write_last_day(date):
    with open(LAST_DAY_FILE, 'w') as outfile:
        outfile.write(date)
    return True

def download_file(url):
    local_filename = url.split('/')[-1]
    with requests.get(url, stream=True) as r:
        with open(local_filename, 'wb') as f:
            shutil.copyfileobj(r.raw, f)

    return local_filename

def pull_pdfs_starting(day):
    """

    :param day:
    :type day: String
    :return:
    """
    today = datetime.datetime.today()
    day_date_obj = datetime.datetime.strptime(day, DATE_FORMAT)
    current_index = day_date_obj
    # >>> today.strftime('%Y/%m/%d')
    i = 0
    pdf_links = []
    with alive_bar((today - day_date_obj).days) as bar:
        while current_index < today:
            today_str = current_index.strftime(DATE_FORMAT)
            text = requests.get("https://addiyar.com/pdf/"+today_str).text
            pdf_link = re.search("(?P<url>https?://[^\s]+.pdf)", text).group("url")
            i+=1
            current_index = day_date_obj + datetime.timedelta(days=i)
            pdf_links.append([pdf_link, today_str])
#            yield
            bar()
    print("fetched this pdf links count: " + str(len(pdf_links)))
    print("Downloading pdfs")
    file_names = []
    with alive_bar(len(pdf_links)) as bar:
        for i in pdf_links:
            file_names.append([download_file(i[0]), i[1]])
            bar()
    print("Resizing, cropping, and extracting images from pdf files")
    today_str = today.strftime(DATE_FORMAT).replace('/', '-')
    print_dir=create_print_dir(today_str)
    with alive_bar(len(file_names)) as bar:
        for i in file_names:
            pages = convert_from_path(i[0], 500, size = (2038, 3426))
            out = pages[10].crop((1026, 302, 1950, 1888))
            out = out.resize((1445, 2480), PIL.Image.ANTIALIAS)
            out.save(print_dir + '/' + i[1].replace('/', '-') + '.png', 'JPEG')
            write_last_day(i[1])
            bar()
    clean(file_names)
    return True

qwe = read_last_day()
pull_pdfs_starting(read_last_day())
