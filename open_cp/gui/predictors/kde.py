"""
kde
~~~

A variety of "other" KDE methods, not drawn directly from the literature.

TODO: The SciPY estimator needs replacing with our own to allow time decay.
"""

from . import predictor
import open_cp.predictors
import tkinter as tk
import tkinter.ttk as ttk
import open_cp.gui.tk.util as util
import open_cp.gui.tk.richtext as richtext
import open_cp.gui.tk.tooltips as tooltips
import open_cp.gui.tk.mtp as mtp
import enum
import numpy as np

_text = {
    "main" : ("Other Kernel Density Estimation methods\n\n"
        + "A selection of other KDE (kernel density estimation) methods; to be compared with "
        + "the 'Scipy KDE naive estimator' (we here offer more options) or the 'Retrospective' and "
        + "'Prospective' hotspotting algorithms (which are explicitly explained in the scientific "
        + "literature, whereas the methods here are not).\n"
        + "We offer two ways to customise the algorithm: the choice of the KDE algorithm to be "
        + "applied to the spacial coordinates (estimating a continuous risk profile from the location "
        + "of events) and how (or not) to weight time.\n\n"
        + "Training Data usage: Can either be ignored, or directly used."
        ),
    "no_data" : "No data points found in time range: have enough crime types been selected?",
    "sk" : "Space kernel: ",
    "sktt" : "How the spatial locations of points are converted to a continuous risk profile",
    "sks" : "Space kernel settings",
    "skernals" : ["Scipy KDE", "Nearest neighbour variable bandwidth"],
    "tk" : "Treatment of timestamps: ",
    "tktt" : "How we should treat timestamps",
    "tks" : "Timestamp adjustment settings",
    "tchoices" : ["Training data only", "All time in window", "Exponential decay", "Quadratic decay"],
    "scipy_main" : "Uses the SciPY builtin Gaussian KDE method.  This is thus like the 'naive' predictor, but with improved control over the usage of time information.",
    "nkde_main" : "Uses a variable bandwidth `k`th nearest neighbour Gaussian KDE.  Tends to identify clusters better.",
    "nkde_k" : "Which nearest neighbour to use:",
    "nkde_k_tt" : "The bandwidth for the contribution to a kernel at a point is chosen by looking at the distance from the point to this nearest neighbour.  Larger values lead to a 'smoother' kernel.  Values in the range 15 to 100 are common.",
    "to_main" : "Only use the training date range of data to compute the kernel.  All points are treated equally.  Probably of mostly academic interest.",
    "wi_main" : "Use all data in a window of time before the prediction date.  All points are treated equally.",
    "wi_days" : "Days in window: ",
    "wi_days_tt" : "The time window will be this many days in length",
    "ex_main" : "The weighting given to points decays exponentially in the time between the event occurring and the prediction date.",
    "ex_scale" : "Scale in days: ",
    "ex_scale_tt" : "The 'scale' of the exponential, which is the time period over which the intensity falls to about 37% of the base intensity.",
    "qu_main" : "The weighting given to points decays exponentially in the time between the event occurring and the prediction date.",
    "qu_scale" : "Scale in days: ",
    "qu_scale_tt" : "The 'scale' of the decay.  The larger this value, the longer in time it takes for events to have less intensity.  See the graph for the effect.",
    "days" : "Days",
    "int" : "Relative weighting",

}

class KDE(predictor.Predictor):
    def __init__(self, model):
        super().__init__(model)
        self.space_kernel = 0
        self._sk_model = [ScipyKDE(), NeatestKDE()]
        self.time_kernel = 0
        self._tk_model = [TrainOnly(), Window(), ExpDecay(), QuadDecay()]
    
    @staticmethod
    def describe():
        return "Kernel density estimation predictor"

    @staticmethod
    def order():
        return predictor._TYPE_GRID_PREDICTOR

    def make_view(self, parent):
        return KDEView(parent, self)

    @property
    def name(self):
        return "KDE predictor ({},{})".format(self.space_kernel.name,
        self.time_kernel.name)
        
    @property
    def settings_string(self):
        # TODO
        return None
        
    def to_dict(self):
        data = {"space_kernel" : self.space_kernel.value}
        data["space_models"] = { model.name : model.to_dict() for model in self._sk_model }
        data["time_models"] = { model.name : model.to_dict() for model in self._tk_model }
        return data
    
    def from_dict(self, data):
        self.space_kernel = int(data["space_kernel"])
        for name, d in data["space_models"].items():
            for model in self._sk_model:
                if model.name == name:
                    model.from_dict(d)
        for name, d in data["time_models"].items():
            for model in self._tk_model:
                if model.name == name:
                    model.from_dict(d)
    
    def make_tasks(self):
        return [self.Task()]
        
    class Task(predictor.GridPredictorTask):
        def __init__(self):
            super().__init__()

        def __call__(self, analysis_model, grid_task, project_task):
            timed_points = self.projected_data(analysis_model, project_task)
            # TODO: Adjust this...
            training_start, _, _, _ = analysis_model.time_range
            timed_points = timed_points[timed_points.timestamps >= training_start]
            if timed_points.number_data_points == 0:
                raise predictor.PredictionError(_text["no_data"])
            grid = grid_task(timed_points)
            # TODO: Return...?

    class SubTask(predictor.SingleGridPredictor):
        def __init__(self, timed_points, grid):
            super().__init__()
            self._timed_points = timed_points
            # TODO

        def __call__(self, predict_time, length):
            pass

    class SpaceKernel(enum.Enum):
        scipy = 0
        nearest = 1

    @property
    def space_kernel(self):
        return self._space_kernel

    @space_kernel.setter
    def space_kernel(self, value):
        self._space_kernel = self.SpaceKernel(value)

    @property
    def space_kernel_model(self):
        return self._sk_model[self.space_kernel.value]

    class TimeKernel(enum.Enum):
        training = 0
        window = 1
        exponential = 2
        quadratic = 3

    @property
    def time_kernel(self):
        return self._time_kernel

    @time_kernel.setter
    def time_kernel(self, value):
        self._time_kernel = self.TimeKernel(value)

    @property
    def time_kernel_model(self):
        return self._tk_model[self.time_kernel.value]


class ScipyKDE():
    def __init__(self):
        pass

    @property
    def name(self):
        return "scipy"

    def to_dict(self):
        return {}

    def from_dict(self, data):
        pass

    def make_view(self, parent):
        return self.View(self, parent)

    class View(ttk.Frame):
        def __init__(self, model, parent):
            super().__init__(parent)
            self.model = model
            util.stretchy_columns(self, [0])
            text = richtext.RichText(self, height=3, scroll="v")
            text.grid(row=0, column=0, sticky=tk.NSEW)
            text.add_text(_text["scipy_main"])


class NeatestKDE():
    def __init__(self):
        self._k = 15

    @property
    def name(self):
        return "nearest"

    def to_dict(self):
        return {"k" : self._k}

    def from_dict(self, data):
        self.k = data["k"]

    @property
    def k(self):
        return self._k

    @k.setter
    def k(self, v):
        self._k = int(v)

    def make_view(self, parent):
        return self.View(self, parent)

    class View(ttk.Frame):
        def __init__(self, model, parent):
            super().__init__(parent)
            self.model = model
            util.stretchy_columns(self, [0])
            text = richtext.RichText(self, height=3, scroll="v")
            text.grid(row=0, column=0, sticky=tk.NSEW)
            text.add_text(_text["nkde_main"])
            frame = ttk.Frame(self)
            frame.grid(row=1, column=0, sticky=tk.W)
            label = ttk.Label(frame, text=_text["nkde_k"])
            label.grid(row=0, column=0, padx=2, pady=2)
            tooltips.ToolTipYellow(label, _text["nkde_k_tt"])
            self._k_value = tk.StringVar()
            entry = ttk.Entry(frame, textvariable=self._k_value)
            entry.grid(row=0, column=1, padx=2, pady=2)
            util.IntValidator(entry, self._k_value, callback=self._k_changed)
            self.update()

        def update(self):
            self._k_value.set(self.model.k)

        def _k_changed(self):
            self.model.k = self._k_value.get()


class TrainOnly():
    def __init__(self):
        pass

    @property
    def name(self):
        return "training dates only"

    def to_dict(self):
        return {}

    def from_dict(self, data):
        pass

    def make_view(self, parent):
        return self.View(self, parent)

    class View(ttk.Frame):
        def __init__(self, model, parent):
            super().__init__(parent)
            self.model = model
            util.stretchy_columns(self, [0])
            text = richtext.RichText(self, height=3, scroll="v")
            text.grid(row=0, column=0, sticky=tk.NSEW)
            text.add_text(_text["to_main"])


class Window():
    def __init__(self):
        self.days = 30

    @property
    def name(self):
        return "time window"

    def to_dict(self):
        return {"days" : self.days}

    def from_dict(self, data):
        self.days = data["days"]

    @property
    def days(self):
        return self._days

    @days.setter
    def days(self, value):
        self._days = float(value)

    def make_view(self, parent):
        return self.View(self, parent)

    class View(ttk.Frame):
        def __init__(self, model, parent):
            super().__init__(parent)
            self.model = model
            util.stretchy_rows_cols(self, [2], [0])
            text = richtext.RichText(self, height=3, scroll="v")
            text.grid(row=0, column=0, sticky=tk.NSEW)
            text.add_text(_text["wi_main"])

            frame = ttk.Frame(self)
            frame.grid(row=1, column=0, sticky=tk.W)
            label = ttk.Label(frame, text=_text["wi_days"])
            label.grid(row=0, column=0, padx=2, pady=2)
            tooltips.ToolTipYellow(label, _text["wi_days_tt"])
            self._days_value = tk.StringVar()
            entry = ttk.Entry(frame, textvariable=self._days_value)
            entry.grid(row=0, column=1, padx=2, pady=2)
            util.FloatValidator(entry, self._days_value, callback=self._days_changed)

            self._plot = mtp.CanvasFigure(self)
            self._plot.grid(row=2, column=0, sticky=tk.NSEW)
            self.update()

        def update(self):
            self._days_value.set(self.model.days)
            def task():
                fig = mtp.new_figure((6,4))
                ax = fig.add_subplot(1,1,1)
                x = [0, self.model.days, self.model.days, self.model.days*1.1]
                y = [1,1,0,0]
                ax.plot(x, y)
                ax.set(xlabel=_text["days"], ylabel=_text["int"], xlim=[0, self.model.days*1.1], ylim=[-0.1,1.1])
                return fig
            self._plot.set_figure_task(task)

        def _days_changed(self):
            self.model.days = self._days_value.get()
            self.update()


class ExpDecay():
    def __init__(self):
        self.scale = 20

    @property
    def name(self):
        return "exponential decay"

    def to_dict(self):
        return {"scale" : self.scale}

    def from_dict(self, data):
        self.scale = data["scale"]

    @property
    def scale(self):
        return self._scale

    @scale.setter
    def scale(self, value):
        self._scale = float(value)

    def make_view(self, parent):
        return self.View(self, parent)

    class View(ttk.Frame):
        def __init__(self, model, parent):
            super().__init__(parent)
            self.model = model
            util.stretchy_rows_cols(self, [2], [0])
            text = richtext.RichText(self, height=3, scroll="v")
            text.grid(row=0, column=0, sticky=tk.NSEW)
            text.add_text(_text["ex_main"])

            frame = ttk.Frame(self)
            frame.grid(row=1, column=0, sticky=tk.W)
            label = ttk.Label(frame, text=_text["ex_scale"])
            label.grid(row=0, column=0, padx=2, pady=2)
            tooltips.ToolTipYellow(label, _text["ex_scale_tt"])
            self._scale_value = tk.StringVar()
            entry = ttk.Entry(frame, textvariable=self._scale_value)
            entry.grid(row=0, column=1, padx=2, pady=2)
            util.FloatValidator(entry, self._scale_value, callback=self._days_changed)

            self._plot = mtp.CanvasFigure(self)
            self._plot.grid(row=2, column=0, sticky=tk.NSEW)
            self.update()

        def update(self):
            self._scale_value.set(self.model.scale)
            def task():
                fig = mtp.new_figure((6,4))
                ax = fig.add_subplot(1,1,1)
                # TODO: Refactor...
                x = np.linspace(0, self.model.scale*5, 100)
                y = np.exp(-x / self.model.scale)
                ax.plot(x, y)
                ax.set(xlabel=_text["days"], ylabel=_text["int"], xlim=[0, self.model.scale*5], ylim=[0,1])
                fig.set_tight_layout("tight")
                return fig
            self._plot.set_figure_task(task)

        def _days_changed(self):
            self.model.scale = self._scale_value.get()
            self.update()


class QuadDecay():
    def __init__(self):
        self.scale = 20

    @property
    def name(self):
        return "quadratic decay"

    def to_dict(self):
        return {"scale" : self.scale}

    def from_dict(self, data):
        self.scale = data["scale"]

    @property
    def scale(self):
        return self._scale

    @scale.setter
    def scale(self, value):
        self._scale = float(value)

    def make_view(self, parent):
        return self.View(self, parent)

    class View(ttk.Frame):
        def __init__(self, model, parent):
            super().__init__(parent)
            self.model = model
            util.stretchy_rows_cols(self, [2], [0])
            text = richtext.RichText(self, height=3, scroll="v")
            text.grid(row=0, column=0, sticky=tk.NSEW)
            text.add_text(_text["qu_main"])

            frame = ttk.Frame(self)
            frame.grid(row=1, column=0, sticky=tk.W)
            label = ttk.Label(frame, text=_text["qu_scale"])
            label.grid(row=0, column=0, padx=2, pady=2)
            tooltips.ToolTipYellow(label, _text["qu_scale_tt"])
            self._scale_value = tk.StringVar()
            entry = ttk.Entry(frame, textvariable=self._scale_value)
            entry.grid(row=0, column=1, padx=2, pady=2)
            util.FloatValidator(entry, self._scale_value, callback=self._days_changed)

            self._plot = mtp.CanvasFigure(self)
            self._plot.grid(row=2, column=0, sticky=tk.NSEW)
            self.update()

        def update(self):
            self._scale_value.set(self.model.scale)
            def task():
                fig = mtp.new_figure((6,4))
                ax = fig.add_subplot(1,1,1)
                # TODO: Refactor...
                x = np.linspace(0, self.model.scale*5, 100)
                y = 1 / (1 + (x / self.model.scale)**2)
                ax.plot(x, y)
                ax.set(xlabel=_text["days"], ylabel=_text["int"], xlim=[0, self.model.scale*5], ylim=[0,1])
                return fig
            self._plot.set_figure_task(task)

        def _days_changed(self):
            self.model.scale = self._scale_value.get()
            self.update()


class KDEView(tk.Frame):
    def __init__(self, parent, model):
        super().__init__(parent)
        self.model = model
        util.stretchy_rows_cols(self, [1], [0])
        self._text = richtext.RichText(self, height=12, scroll="v")
        self._text.grid(row=0, column=0, sticky=tk.NSEW)
        self._text.add_text(_text["main"])
        frame = ttk.Frame(self)
        self.add_widgets(frame)
        frame.grid(row=1, column=0, sticky=tk.NSEW)
        self.update()
    
    def update(self):
        self._update_space()
        self._update_time()
    
    def add_widgets(self, frame):
        util.stretchy_rows_cols(frame, [1], [0,1])

        subframe = ttk.Frame(frame)
        subframe.grid(row=0, column=0, sticky=tk.NSEW, padx=1, pady=1)
        label = ttk.Label(subframe, text=_text["sk"])
        label.grid(row=0, column=0, padx=2)
        tooltips.ToolTipYellow(label, _text["sktt"])
        self._space_cbox = ttk.Combobox(subframe, height=5, state="readonly", width=40,
            values=_text["skernals"])
        self._space_cbox.bind("<<ComboboxSelected>>", self._space_changed)
        self._space_cbox.grid(row=0, column=1, padx=2)
        self._space_frame = ttk.LabelFrame(frame, text=_text["sks"])
        self._space_frame.grid(row=1, column=0, sticky=tk.NSEW, padx=1, pady=1)
        util.stretchy_rows_cols(self._space_frame, [0], [0])

        subframe = ttk.Frame(frame)
        subframe.grid(row=0, column=1, sticky=tk.NSEW, padx=1, pady=1)
        label = ttk.Label(subframe, text=_text["tk"])
        label.grid(row=0, column=0, padx=2)
        tooltips.ToolTipYellow(label, _text["tktt"])
        self._time_cbox = ttk.Combobox(subframe, height=5, state="readonly", width=40,
            values=_text["tchoices"])
        self._time_cbox.bind("<<ComboboxSelected>>", self._time_changed)
        self._time_cbox.grid(row=0, column=1, padx=2)
        self._time_frame = ttk.LabelFrame(frame, text=_text["tks"])
        self._time_frame.grid(row=1, column=1, sticky=tk.NSEW, padx=1, pady=1)
        util.stretchy_rows_cols(self._time_frame, [0], [0])

    def _space_changed(self, event=None):
        self.model.space_kernel = int(self._space_cbox.current())
        self._update_space()

    def _update_space(self):
        self._space_cbox.current(self.model.space_kernel.value)
        for w in self._space_frame.winfo_children():
            w.destroy()
        view = self.model.space_kernel_model.make_view(self._space_frame)
        view.grid(sticky=tk.NSEW)

    def _time_changed(self, event=None):
        self.model.time_kernel = int(self._time_cbox.current())
        self._update_time()

    def _update_time(self):
        self._time_cbox.current(self.model.time_kernel.value)
        for w in self._time_frame.winfo_children():
            w.destroy()
        view = self.model.time_kernel_model.make_view(self._time_frame)
        view.grid(sticky=tk.NSEW)


def test(root):
    ll = KDE(predictor.test_model())
    predictor.test_harness(ll, root)
