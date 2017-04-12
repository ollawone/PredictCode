"""
sepp
~~~~

Implements the ETAS (Epidemic Type Aftershock-Sequences) model intensity
estimation scheme outlined in Mohler et al. (2011).

As this is a statistical model, we separate out the statistical optimisation
procedure into a separate class, :class StocasticDecluster:  This allows
testing and exploration of the model without worry about real world issues such
as time-stamps.  

We can think of this algorithm in terms of a "machine learning" workflow, and
separate a "training" stage from a "prediction" stage.  The statistical model
is that we have a "background" rate of random events, and then that existing
events cause a time/space localised increase in risk, described by a "trigger"
kernel.  The trigger kernel does not vary with the time/space location of the
event (which is perhaps a limit of the model).  As such, both the background
and trigger kernels should be fairly constant in time, and so if "trained"
on historical data, should be valid to make predictions for, say, the next
few weeks or months.  (Over long time scales, we should expect the background
kernel to change.)

This is also useful in practise, as the training stage is slow, but once
trained, the kernels can quickly be evaluated to make predictions.

References
~~~~~~~~~~
Mohler et al, "Self-Exciting Point Process Modeling of Crime",
   Journal of the American Statistical Association, 2011
   DOI: 10.1198/jasa.2011.ap09546

Rosser, Cheng, "Improving the Robustness and Accuracy of Crime Prediction with
the Self-Exciting Point Process Through Isotropic Triggering"
   Appl. Spatial Analysis
   DOI: 10.1007/s12061-016-9198-y
"""

from . import predictors
from . import kernels
import numpy as _np

def _normalise_matrix(p):
    column_sums = _np.sum(p, axis=0)
    return p / column_sums[None,:]

def p_matrix(points, background_kernel, trigger_kernel):
    """Computes the probability matrix.

    :param points: The (time, x, y) data
    :param background_kernel: The kernel giving the background event intensity.
    :param trigger_kernel: The kernel giving the triggered event intensity.

    :return: A matrix `p` such that `p[i][i]` is the probability event `i` is a
    background event, and `p[i][j]` is the probability event `j` is triggered
    by event `i`.
    """

    number_data_points = points.shape[-1]
    p = _np.zeros((number_data_points, number_data_points))
    for j in range(1, number_data_points):
        d = points[:, j][:,None] - points[:, :j]
        p[0:j, j] = trigger_kernel(d)
    b = background_kernel(points)
    for i in range(number_data_points):
        p[i, i] = b[i]
    return _normalise_matrix(p)

def p_matrix_fast(points, background_kernel, trigger_kernel, time_cutoff=150, space_cutoff=1):
    """Computes the probability matrix.  Offers faster execution speed than
    :function:`p_matrix` by, in the calculation of triggered event
    probabilities, ignoring events which are beyond a space or time cutoff.
    These parameters should be set so that the `trigger_kernel` evaluates to
    (very close to) zero outside the cutoff zone.

    :param points: The (time, x, y) data
    :param background_kernel: The kernel giving the background event intensity.
    :param trigger_kernel: The kernel giving the triggered event intensity.
    :param time_cutoff: The maximum time between two events which can be
    considered in the trigging calculation.
    :param space_cutoff: The maximum (two-dimensional Eucliean) distance
    between two events which can be considered in the trigging calculation.

    :return: A matrix `p` such that `p[i][i]` is the probability event `i` is a
    background event, and `p[i][j]` is the probability event `j` is triggered
    by event `i`.
    """

    number_data_points = points.shape[-1]
    p = _np.zeros((number_data_points, number_data_points))
    space_cutoff_sq = space_cutoff**2
    for j in range(1, number_data_points):
        d = points[:, j][:,None] - points[:, :j]
        dmask = (d[0] <= time_cutoff) & ((d[1]**2 + d[2]**2) <= space_cutoff_sq)
        d = d[:, dmask]
        if d.shape[-1] == 0:
            continue
        p[0:j, j][dmask] = trigger_kernel(d)
    p += _np.diag(background_kernel(points))
    return _normalise_matrix(p)

def initial_p_matrix(points, initial_time_bandwidth = 0.1,
        initial_space_bandwidth = 50.0):
    """Returns an initial estimate of the probability matrix.  Uses a Gaussian
    kernel in space, and an exponential kernel in time, both non-normalised.
    Diagonal (i.e. background "probabilities") are set to 1.  Finally the
    matrix is normalised.

    :param points: The (time, x, y) data.
    :param initial_time_bandwidth: The "scale" of the exponential.
    :param initial_space_bandwidth: The standard deviation of the Gaussian.
    """

    def bkernel(pts):
        return _np.zeros(pts.shape[-1]) + 1
    def tkernel(pts):
        time = _np.exp( - pts[0] / initial_time_bandwidth )
        norm = 2 * initial_space_bandwidth ** 2
        space = _np.exp( - (pts[1]**2 + pts[2]**2) / norm )
        return time * space
    return p_matrix(points, bkernel, tkernel)

def sample_points(points, p):
    """Using the probability matrix, sample background and triggered points.

    :param points: The (time, x, y) data.
    :param p: The probability matrix.

    :return: A pair of `(backgrounds, triggered)` where `backgrounds` is the
    (time, x, y) data of the points classified as being background events,
    and `triggered` is the (time, x, y) *delta* of the triggered events.
    That is, `triggered` represents the difference in space and time between
    each triggered event and the event which triggered it, as sampled from the
    probability matrix.
    """

    number_data_points = points.shape[-1]
    choice = _np.array([ _np.random.choice(j+1, p=p[0:j+1, j])
        for j in range(number_data_points) ])
    mask = ( choice == _np.arange(number_data_points) )
    
    backgrounds = points[:,mask]
    triggered = (points - points[:,choice])[:,~mask]
    return backgrounds, triggered

def make_kernel(data, background_kernel, trigger_kernel):
    """Produce a kernel object which evaluates the background kernel, and
    the trigger kernel based on the space-time locations in the data.

    :param data: An array of shape `(3,N)` giving the space-time locations
    events.  Used when computing the triggered / aftershock events.
    :param background_kernel: The kernel object giving the background risk
    intensity.
    :param trigger_kernel: The kernel object giving the trigger / aftershock
    risk intensity.
    
    :return: A kernel object which can be called on arrays on points.
    """
    data_copy = _np.array(data)
    def one_dim_kernel(pt):
        mask = data_copy[0] < pt[0]
        bdata = data_copy[:,mask]
        if bdata.shape[-1] == 0:
            return background_kernel(pt)
        return background_kernel(pt) + _np.sum(trigger_kernel(pt[:,None] - bdata))
    def kernel(points):
        points = _np.asarray(points)
        if len(points.shape) == 1:
            return one_dim_kernel(points)
        out = _np.empty(points.shape[-1])
        for i, pt in enumerate(points.T):
            out[i] = one_dim_kernel(pt)
        return out
    return kernel


class StocasticDecluster():
    """Implements the 'stocastic declustering algorithm' from Mohler et al
    (2011).  This allows estimation of two time-space kernels, one for the
    background events, and one the 'trigger' kernel which elevates risk
    according to past events.
    
    This class works with floating-point data, and exposes elements of the
    underlying optimisation algorithm.  It is designed for testing and
    experimentation.

    :param background_kernel_estimator: The kernel estimator to use for
    background events.
    :param trigger_kernel_estimator: The kernel estimator to use for triggered
    / aftershock events.
    :param initial_time_bandwidth: The bandwidth in time to use when making an
    initial classification of data into background or triggered events.  Default
    is 0.1 day**(-1) in units of minutes (so 0.1*24*60).
    :param initial_space_bandwidth: The bandwidth in space to use when making
    an initial classification of data into background or triggered events.
    Default is 50 units.
    :param space_cutoff: The maximum distance we believe the triggered kernel
    will extend to in space.  Decrease this to improve the speed of the
    estimation, at the cost of possibly missing data.  Default is 500 units.
    :param time_cutoff: The maximum distance we believe the triggered kernel
    will extend to in time.  Decrease this to improve the speed of the
    estimation, at the cost of possibly missing data.  Default is 120 days,
    in units of minutes (so 120*24*60).
    :param points: The three dimensional data.  `points[0]` is the times of
    events, and `points[1]` and `points[2]` are the x and y coordinates.
    """

    def __init__(self, background_kernel_estimator = None,
            trigger_kernel_estimator = None,
            initial_time_bandwidth = 0.1 * (_np.timedelta64(1, "D") / _np.timedelta64(1, "m")),
            initial_space_bandwidth = 50.0,
            space_cutoff = 500.0,
            time_cutoff = 120 * (_np.timedelta64(1, "D") / _np.timedelta64(1, "m")),
            points = None):
        self.background_kernel_estimator = background_kernel_estimator
        self.trigger_kernel_estimator = trigger_kernel_estimator
        self.initial_time_bandwidth = initial_time_bandwidth
        self.initial_space_bandwidth = initial_space_bandwidth
        self.space_cutoff = space_cutoff
        self.time_cutoff = time_cutoff
        self.points = points

    def next_iteration(self, p):
        """Perform a single iteration of the optimisation algorithm:
        1. Samples background and triggered events using the p matrix.
        2. Estimates kernels from these samples.
        3. Normalises these kernels.
        4. Computes the new p matrix from these kernels.

        :param p: The matrix of probabilities to sample from.

        :return: A triple `(p, bkernel, tkernel)` where `p` is the new
        probability matrix, `bkernel` the kernel for background events used to
        compute `p`, and `tkernel` the kernel for triggered events.
        """
        
        backgrounds, triggered = sample_points(self.points, p)
        bkernel = self.background_kernel_estimator(backgrounds)
        tkernel = self.trigger_kernel_estimator(triggered)

        number_events = self.points.shape[-1]
        number_background_events = backgrounds.shape[-1]
        number_triggered_events = number_events - number_background_events
        bkernel.set_scale(number_background_events)
        tkernel.set_scale(number_triggered_events / number_events)
        pnew = p_matrix_fast(self.points, bkernel, tkernel,
            time_cutoff = self.time_cutoff, space_cutoff = self.space_cutoff)
        return pnew, bkernel, tkernel
    
    def run_optimisation(self, iterations=20):
        """Runs the optimisation algorithm by taking an initial estimation of
        the probability matrix, and then running the optimisation step.  If
        this step ever classifies most events as background, or as triggered,
        then optimisation will fail.  Tuning the initial bandwidth parameters
        may help.

        :param iterations: The number of optimisation steps to perform.

        :return: :class:`OptimisationResult`
        """
        p = initial_p_matrix(self.points, self.initial_time_bandwidth, self.initial_space_bandwidth)
        errors = []
        for _ in range(iterations):
            pnew, bkernel, tkernel = self.next_iteration(p)
            errors.append(_np.sum((pnew - p) ** 2))
            p = pnew
        kernel = make_kernel(self.points, bkernel, tkernel)
        return OptimisationResult(kernel=kernel, p=p, background_kernel=bkernel,
            trigger_kernel=tkernel, ell2_error=_np.sqrt(_np.asarray(errors)),
            time_cutoff=self.time_cutoff, space_cutoff=self.space_cutoff)


class OptimisationResult():
    """Contains results of the optimisation process.

    :param kernel: the overall estimated intensity kernel.
    :param p: the estimated probability matrix.
    :param background_kernel: the estimatede background event intensity kernel.
    :param trigger_kernel: the estimated triggered event intensity kernel.
    :param ell2_error: an array of the L^2 differences between successive
    estimates of the probability matrix.  That these decay is a good indication
    of convergence.
    :param time_cutoff: Optionally specify the maximum time extent of the
    trigger_kernel used in calculations.
    :param space_cutoff: Optionally specify the maximum space extent of the
    trigger_kernel used in calculations.
    """
    def __init__(self, kernel, p, background_kernel, trigger_kernel, ell2_error,
            time_cutoff=None, space_cutoff=None):
        self.kernel = kernel
        self.p = p
        self.background_kernel = background_kernel
        self.trigger_kernel = trigger_kernel
        self.ell2_error = ell2_error
        self.time_cutoff = time_cutoff
        self.space_cutoff = space_cutoff


def make_space_kernel(data, background_kernel, trigger_kernel, time,
        time_cutoff=None, space_cutoff=None):
    """Produce a kernel object which evaluates the background kernel, and
    the trigger kernel based on the space locations in the data, always using
    the fixed time as passed in.

    :param data: An array of shape `(3,N)` giving the space-time locations
    events.  Used when computing the triggered / aftershock events.
    :param background_kernel: The kernel object giving the background risk
    intensity.  We assume this has a method `space_kernel` which gives just
    the two dimensional spacial kernel.
    :param trigger_kernel: The kernel object giving the trigger / aftershock
    risk intensity.
    :param time: The fixed time coordinate to evaluate at.
    :param time_cutoff: Optional; if set, then we assume the trigger_kernel is
    zero for times greater than this value (to speed up evaluation).
    :param space_cutoff: Optional; if set, then we assume the trigger_kernel is
    zero for space distances greater than this value (to speed up evaluation).
    
    :return: A kernel object which can be called on arrays of (2 dimensional
    space) points.
    """
    mask = data[0] < time
    if time_cutoff is not None:
        mask = mask & (data[0] > time - time_cutoff)
    data_copy = _np.array(data[:, mask])
    def kernel(points):
        x = _np.atleast_1d(_np.asarray(points[0]))
        y = _np.atleast_1d(_np.asarray(points[1]))
        t = _np.zeros_like(x) + time
        back = _np.atleast_1d(background_kernel(_np.vstack((t,x,y))))
        if data_copy.shape[-1] > 0:
            # In principle this is quicker, but we end up evaluating `trigger_kernel`
            # on a large numpy array, and if `trigger_kernel` also manipulates large
            # arrays (it does, in our case!) you end with a massive array and out of memory.
            #t = _np.zeros_like(x) + time
            #p = _np.vstack([t,x,y])
            #combined = p[...,None] - now_data[:,None,:]
            #out = trigger_kernel(combined.reshape(3, combined.shape[1] * combined.shape[2]))
            #out = out.reshape((combined.shape[1], combined.shape[2]))
            #back += _np.sum(out, axis=1)
            for i,(xx,yy) in enumerate(zip(x,y)):
                pts = _np.array([time,xx,yy])[:,None] - data_copy
                if space_cutoff is not None:
                    mask = pts[1]**2 + pts[2]**2 < space_cutoff**2
                    pts = pts[:, mask]
                    if pts.shape[-1] == 0:
                        continue
                back[i] += _np.sum(trigger_kernel(pts))
        return back
    return kernel


class AverageTimeAdjustedKernel(kernels.Kernel):
    """Wraps a :class Kernel: instance, which supports the `space_kernel` and
    `time_kernel` interface, and builds a new kernel which is constant in time.
    The time intensity is computed by taking an average of the middle half
    of the original time kernel.

    :param kernel: The original kernel to delegate to.
    :param time_end: We assume that the original kernel is roughly correct
    for times in the range 0 to `time_end`.
    """
    def __init__(self, kernel, time_end):
        self.delegate = kernel
        self.time_average = self._average_time(kernel, time_end)

    def _average_time(self, kernel, time_end):
        start = time_end / 4
        points = _np.random.random(100) * time_end / 2 + start
        return _np.mean(kernel.time_kernel(points))

    def time_kernel(self, points):
        return _np.zeros_like(_np.asarray(points)) + self.time_average

    def space_kernel(self, points):
        return self.delegate.space_kernel(points)

    def __call__(self, points):
        return self.time_average * self.space_kernel(points[1:])

    def set_scale(self, value):
        self.delegate.set_scale(value)


class SEPPPredictor(predictors.DataTrainer):
    """Returned by :class SEPPTrainer: encapsulated computed background and
    triggering kernels.  This class allows these to be evaluated on potentially
    different data to produce predictions.

    When making a prediction, the *time* component of the background kernel
    is ignored.  This is allowed, because the kernel estimation used looks
    at time and space separately for the background kernel.  We do this because
    KDE methods don't allow us to "predict" into the future.

    This class also stores information about the optimisation procedure.
    """
    def __init__(self, result, epoch_start, epoch_end):
        self.result = result
        time = (epoch_end - epoch_start) / _np.timedelta64(1, "m")
        self.adjusted_background_kernel = AverageTimeAdjustedKernel(
            self.result.background_kernel, time)
        # The start and end time of the _training_ data
        self.epoch_start = epoch_start
        self.epoch_end = epoch_end

    @property
    def background_kernel(self):
        """The original, non-adjusted background kernel estimated by the
        training algorithm."""
        return self.result.background_kernel

    @property
    def trigger_kernel(self):
        """The trigger / aftershock kernel estimated by the training
        algorithm."""
        return self.result.trigger_kernel

    def predict(self, predict_time, cutoff_time=None):
        """Make a prediction at a time, using the data held by this instance.
        That is, evaluate the background kernel plus the trigger kernel at
        events before the prediction time.  Optionally you can limit the data
        used, though this is against the underlying statistical model.

        :param predict_time: Time point to make a prediction at.
        :param cutoff_time: Optionally, limit the input data to only be from
        before this time.

        :return: Instance of :class predictors.ContinuousPrediction:
        """
        events = self.data.events_before(cutoff_time)
        times = (events.timestamps - self.epoch_start) / _np.timedelta64(1, "m")
        predict_time = _np.datetime64(predict_time)
        time = (predict_time - self.epoch_start) / _np.timedelta64(1, "m")
        data = _np.vstack((times, events.xcoords, events.ycoords))
        kernel = make_space_kernel(data, self.background_kernel, self.trigger_kernel,
            time, self.result.time_cutoff, self.result.space_cutoff)
        return predictors.KernelRiskPredictor(kernel)


class SEPPTrainer(predictors.DataTrainer):
    """Use the algorithm described in Mohler et al. 2011.  The kernel
    estimation used is the "kth nearest neighbour variable bandwidth Gaussian"
    KDE.  This is a two-step algorithm: this class "trains" itself on data,
    and returns a class which can then make predictions, possibly on other
    data.

    :param k_time: The kth nearest neighbour to use in the KDE of the time
    kernel; defaults to 100.
    :param k_space: The kth nearest neighbour to use in the KDE of space and
    space/time kernels; defaults to 15.
    """
    def __init__(self, k_time=100, k_space=15):
        self.k_time = k_time
        self.k_space = k_space # TODO: Shouldn't expose this, as changing it is unpredictable
        self._space_cutoff = 500
        self._time_cutoff = 120 * 24 * 60 # minutes
        self._trigger_kernel_estimator = kernels.KthNearestNeighbourGaussianKDE(self.k_space)

    @property
    def trigger_kernel_estimator(self):
        """The kernel estimator to use for triggered events.  Defaults to a kth
        nearest neighbour variable-bandwidth Gaussian kernel estimator with the
        value of `k` set in the constructor.
        """
        return self._trigger_kernel_estimator

    @trigger_kernel_estimator.setter
    def trigger_kernel_estimator(self, estimator):
        self._trigger_kernel_estimator = estimator

    @property
    def space_cutoff(self):
        """To speed up optimisation, set this to the minimal distance at which
        we think the spacial triggering will be effectively zero.  For real
        data, 500m is a reasonable estimate.
        """
        return self._space_cutoff

    @space_cutoff.setter
    def space_cutoff(self, value):
        self._space_cutoff = value

    @property
    def time_cutoff(self):
        """To speed up optimisation, set this to the minimal time gap at which
        we think the spacial triggering will be effectively zero.  For real
        data, 120 days is a reasonable estimate.
        """
        return self._time_cutoff * _np.timedelta64(60, "s")

    @time_cutoff.setter
    def time_cutoff(self, value):
        self._time_cutoff = _np.timedelta64(value) / _np.timedelta64(1, "m")

    def as_time_space_points(self, cutoff_time=None):
        """Return a copy of the input data as an array of shape (3,N) of
        time/space points (without units), as used by the declustering
        algorithm.  Useful when trying to understand what the algorithm is
        doing.
        """
        events = self.data.events_before(cutoff_time)
        return events.to_time_space_coords()

    def train(self, cutoff_time=None, iterations=40):
        """Perform the (slow) training step on historical data.  This estimates
        kernels, and returns an object which can make predictions.

        :param cutoff_time: If specified, then limit the historical data to
        before this time.
        
        :return: A :class SEPPPredictor: instance.
        """
        decluster = StocasticDecluster()
        decluster.trigger_kernel_estimator = self._trigger_kernel_estimator
        decluster.background_kernel_estimator = kernels.KNNG1_NDFactors(self.k_time, self.k_space)
        # From Rosser, Cheng, suggested 0.1 day^{-1} and 50 metres
        decluster.initial_time_bandwidth = 24 * 60 / 10 # minutes
        decluster.initial_space_bandwidth = 50.0
        decluster.space_cutoff = self._space_cutoff
        decluster.time_cutoff = self._time_cutoff
        decluster.points = self.as_time_space_points(cutoff_time)
        result = decluster.run_optimisation(iterations=iterations)
        return SEPPPredictor(result, self.data.timestamps[0], self.data.timestamps[-1])