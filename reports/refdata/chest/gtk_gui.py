import gi
gi.require_version('Gtk', '3.0')
from gi.repository import Gtk
from datetime import datetime

def process_dates(current_period_start, current_period_end, current_knowledge_end,
                  prior_period_start, prior_period_end, prior_knowledge_end):
    print(f"Received dates: {current_period_start}, {current_period_end}, {current_knowledge_end}, "
          f"{prior_period_start}, {prior_period_end}, {prior_knowledge_end}")

class DateApp(Gtk.Window):
    def __init__(self):
        Gtk.Window.__init__(self, title="DateApp")
        self.set_border_width(10)

        vbox = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=6)
        self.add(vbox)

        # Hardcoded dates for testing purpose
        self.current_period_start = "2023-09-20:15:30:00"
        self.current_period_end = "2023-09-25:15:30:00"
        self.current_knowledge_end = "2023-09-22:15:30:00"
        self.prior_period_start = "2023-09-15:15:30:00"
        self.prior_period_end = "2023-09-19:15:30:00"
        self.prior_knowledge_end = "2023-09-17:15:30:00"

        submit_button = Gtk.Button(label="Submit Dates")
        submit_button.connect("clicked", self.on_submit)
        vbox.pack_start(submit_button, True, True, 0)

    def on_submit(self, button):
        date_format = "%Y-%m-%d:%H:%M:%S"

        # Parsing the hardcoded dates
        current_period_start = datetime.strptime(self.current_period_start, date_format)
        current_period_end = datetime.strptime(self.current_period_end, date_format)
        current_knowledge_end = datetime.strptime(self.current_knowledge_end, date_format)
        prior_period_start = datetime.strptime(self.prior_period_start, date_format)
        prior_period_end = datetime.strptime(self.prior_period_end, date_format)
        prior_knowledge_end = datetime.strptime(self.prior_knowledge_end, date_format)

        # Calling the process_dates function and passing the parsed dates
        process_dates(current_period_start, current_period_end, current_knowledge_end,
                      prior_period_start, prior_period_end, prior_knowledge_end)

win = DateApp()
win.connect("destroy", Gtk.main_quit)
win.show_all()
Gtk.main()
