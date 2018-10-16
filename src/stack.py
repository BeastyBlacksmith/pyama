#! /usr/bin/env python3
import random
import re
import string
import tempfile
import threading
import warnings
import xml.etree.ElementTree as ET

import numpy as np
import tifffile
import PIL.Image as pilimg
import PIL.ImageTk as piltk
import skimage.draw as skid

from listener import Listeners


class Stack:
    """Represents an image stack.

    :param path: (optional) path to a file holding a TIFF stack
    :type path: str
    """

    def __init__(self, path=None):
        """Initialize a stack."""
        self.image_lock = threading.RLock()
        self.info_lock = threading.RLock()
        self.roi_lock = threading.RLock()
        self._listeners = Listeners(kinds={"roi", "image"})
        self._clear_state()

        # If requested, load stack
        if path is not None:
            self.load(path)


    def _clear_state(self):
        """Clear the internal state"""
        with self.image_lock:
            # The stack path and object
            self._path = None
            self.img = None
            self._tmpfile = None

            # The stack properties
            self._mode = None
            self._order = None
            self._width = 0
            self._height = 0
            self._n_images = 0
            self._n_frames = 0
            self._n_channels = 0

        # ROI list
        with self.roi_lock:
            self._rois = {}

        # Clear image information
        self.clear_info()

        # Notify listeners
        self._listeners.notify(kind=None)


    def load(self, path):
        """Load a stack from a path."""
        with self.image_lock:
            try:
                # Open image file
                self._path = path
                tiff = tifffile.TiffFile(self._path)
                pages = tiff.pages
                if not pages:
                    raise ValueError(f"Cannot open file '{self._path}': No pages found in TIFF.")

                # Get basic information
                self._n_images = len(pages)
                page0 = pages[0]
                self._width = page0.imagewidth
                self._height = page0.imagelength
                self._mode = page0.bitspersample
                if self._mode != 8 and self._mode != 16:
                    raise TypeError(f"Only 8-bit and 16-bit images are supported; found {self._mode}.")

                # Get software-specific information
                description = page0.description
                if page0.is_imagej:
                    self._parse_imagej_tags(description)
                elif page0.is_ome:
                    self._parse_ome(description)
                else:
                    raise TypeError("Unknown image type.")

                # Copy stack to numpy array in temporary file
                self._tmpfile = tempfile.TemporaryFile()
                dtype = np.uint8 if self._mode == 8 else np.uint16
                self.img = np.memmap(filename=self._tmpfile,
                                     dtype=dtype,
                                     shape=(self._n_channels,
                                            self._n_frames,
                                            self._height,
                                            self._width))
                for i in range(self._n_images):
                    ch, fr = self.convert_position(image=i)
                    pages[i].asarray(out=self.img[ch,fr,:,:])

            except Exception as e:
                self._clear_state()
                print(str(e))
                raise

            finally:
                # Close TIFF image
                tiff.close()

                self._listeners.notify("image")


    def close(self):
        """Close the TIFF file."""
        with self.image_lock:
            self.img = None
            self._tmpfile.close()
            self._tmpfile = None
            self._clear_state()


    def _parse_imagej_tags(self, desc):
        """Read stack dimensions from ImageJ’s TIFF description tag."""
        # Set dimension order
        self._order = "tc"

        # Get number of frames in stack
        m = re.search(r"frames=(\d+)", desc)
        if m:
            self._n_frames = int(m.group(1))
        else:
            self._n_frames = 1

        # Get number of slices in stack
        m = re.search(r"slices=(\d+)", desc)
        if m:
            n_slices = int(m.group(1))
            if self._n_frames == 1 and n_slices > 1:
                self._n_frames = n_slices
            elif n_frames > 1:
                raise ValueError("Bad image format: multiple slices and frames detected.")

        # Get number of channels in stack
        m = re.search(r"channels=(\d+)", desc)
        if m:
            self._n_channels = int(m.group(1))
        else:
            self._n_channels = 1


    def _parse_ome(self, ome):
        """Extract stack information from description in OME format."""
        root = ET.fromstring(ome)

        # Find XML namespace
        # The namespace of an XML tag is prefixed to the tag name in
        # curly braces; see documentation of `xml.etree.ElementTree`.
        idx = root.tag.rfind('}')
        if idx == -1:
            xmlns = ''
        else:
            xmlns = root.tag[:idx+1]

        # Find "Image" tag
        tag_image = ''.join((xmlns, "Image"))
        for child in root:
            if child.tag == tag_image:
                element_image = child
                break
        else:
            raise TypeError("No 'Image' tag found in OME description.")

        # Find "Pixels" tag
        tag_pixels = ''.join((xmlns, "Pixels"))
        for child in element_image:
            if child.tag == tag_pixels:
                element_pixels = child
                break
        else:
            raise TypeError("No 'Pixels' tag found in OME description.")

        # Get image properties from attributes of "Pixels" tag
        # Number of frames
        sizeT = element_pixels.attrib.get("SizeT")
        if sizeT is None:
            raise ValueError("No 'SizeT' attribute found in OME description.")
        try:
            sizeT = int(sizeT)
        except:
            raise ValueError("Bad 'SizeT' value in OME description.")
        if sizeT < 1:
            raise ValueError("Non-positive 'SizeT' value in OME description.")
        self._n_frames = sizeT

        # Number of channels
        sizeC = element_pixels.attrib.get("SizeC")
        if sizeC is None:
            raise ValueError("No 'SizeC' attribute found in OME description.")
        try:
            sizeC = int(sizeC)
        except:
            raise ValueError("Bad 'SizeC' value in OME description.")
        if sizeC < 1:
            raise ValueError("Non-positive 'SizeC' value in OME description.")
        self._n_channels = sizeC

        # Number of slices
        sizeZ = element_pixels.attrib.get("SizeZ")
        if sizeZ is None:
            raise ValueError("No 'SizeZ' attribute found in OME description.")
        try:
            sizeZ = int(sizeZ)
        except:
            raise ValueError("Bad 'SizeZ' value in OME description.")
        if sizeZ < 1:
            raise ValueError("Non-positive 'SizeZ' value in OME description.")
        elif sizeZ != 1:
            raise ValueError(f"Only images with one slice supported; found {sizeZ} slices.")

        # Dimension order
        dim_order = element_pixels.attrib.get("DimensionOrder")
        if dim_order is None:
            raise ValueError("No 'DimensionOrder' attribute found in OME description.")
        idx_C = dim_order.find('C')
        idx_T = dim_order.find('T')
        if idx_C == -1 or idx_T == -1:
            raise ValueError("Bad 'DimensionOrder' value in OME description.")
        if idx_C < idx_T:
            self._order = 'tc'
        else:
            self._order = 'ct'


    def convert_position(self, channel=None, frame=None, image=None):
        """
        Convert stack position between (channel, frame) and image.
        
        Either give "channel" and "frame" to obtain the corresponding
        image index, or give "image" to obtain the corresponding indices
        of channel and frame as tuple.
        All other combinations will return None.
        """
        # Check arguments
        if channel is None and frame is None:
            to2 = True
        elif channel is None or frame is None:
            return None
        else:
            to2 = False
        if image is None and to2:
            return None

        # Convert
        with self.image_lock:
            if self._order is None:
                return None

            elif self._order == "tc":
                if to2:
                    channel = image % self._n_channels
                    frame = image // self._n_channels
                    return (channel, frame)
                else:
                    image = frame * self._n_channels + channel
                    return image

            elif self._order == "ct":
                if to2:
                    channel = image // self._n_frames
                    frame = image % self._n_frames
                    return (channel, frame)
                else:
                    image = channel * self._n_frames + frame
                    return image

            else:
                raise NotImplementedError(f"Dimension order '{self._order}' not implemented yet.")


    def get_image(self, channel, frame):
        """Get a numpy array of a stack position."""
        with self.image_lock:
            return self.img[channel, frame, :, :]


    def get_image_copy(self, channel, frame):
        """Get a copy of a numpy array of a stack position."""
        with self.image_lock:
            return self.img[channel, frame, :, :].copy()


    def get_frame_tk(self, channel, frame, convert_fcn=None):
        """
        Get a frame of the stack as :py:class:`tkinter.PhotoImage`.

        :param channel: The channel of the requested stack position
        :type channel: int
        :param frame: The frame of the requested stack position
        :type frame: int
        :param convert_fcn: Custom conversion function
        :type convert_fcn: None or function

        If a custom conversion function is given, the function must take
        one argument, which is a (n_rows, n_columns)-shaped numpy array
        of the current stack position with the bit-depth of the original
        image (typically 8 or 16 bit per pixel), and must return
        a (n_rows, n_columns)-shaped numpy array of ``uint8`` type.

        :return: the image at the requested stack position
        :rtype: :py:class:`tkinter.PhotoImage`
        """
        with self.image_lock:
            if convert_fcn:
                a8 = convert_fcn(self.get_image(channel, frame))
            elif self._mode == 8:
                a8 = self.get_image(channel, frame)
            elif self._mode == 16:
                a16 = self.get_image(channel, frame)
                a8 = np.empty(a16.shape, dtype=np.uint8)
                np.floor_divide(a16, 256, out=a8)
                #a16 = a16 - a16.min()
                #a16 = a16 / a16.max() * 255
                #np.floor_divide(a16, 255, out=a8)
                #np.true_divide(a16, 255, out=a8, casting='unsafe')
            else:
                raise ValueError(f"Illegal image mode: {self._mode}")
            return piltk.PhotoImage(pilimg.fromarray(a8, mode='L'))


    def clear_info(self):
        """Clear the image information"""
        with self.info_lock:
            self._info = {}


    def update_info(self, name, value):
        with self.info_lock:
            self._info[name] = value


    def get_info(self, name):
        with self.info_lock:
            return self._info.get(name)


    def stack_info(self):
        """Print stack info. Only for debugging."""
        with self.image_lock:
            print("Path: " + str(self._path))
            print("width: " + str(self._width))
            print("height: " + str(self._height))
            print("n_images: " + str(self._n_images))
            print("n_channels: " + str(self._n_channels))
            print("n_frames: " + str(self._n_frames))


    def add_listener(self, fun, kind=None):
        """Register a listener to stack changes."""
        return self._listeners.register(fun, kind)


    def delete_listener(self, lid):
        """Un-register a listener."""
        self._listeners.delete(lid)


    def set_rois(self, rois, type_, frame=Ellipsis):
        """Set the ROI set of the stack.

        :param rois: The ROIs to be set
        :param type_: The ROI type (currently one of "rect" and "raw")
        :param frame: The frame to which the ROI belongs. ``Ellipsis`` stands for all frames.

        For details, see :py:class:`RoiSet`.
        """
        with self.roi_lock:
            self._rois[frame] = RoiSet(rois, type_)
            self._listeners.notify("roi")


    @property
    def rois(self):
        with self.roi_lock:
            return self._rois


    def get_rois(self, frame=None):
        with self.roi_lock:
            return self._rois.get(frame)


    def clear_rois(self, frame=None):
        """Delete the current ROI set"""
        with self.roi_lock:
            if frame is None:
                self._rois = {}
            else:
                del self._rois[frame]
            self._listeners.notify("roi")


    @property
    def path(self):
        with self.image_lock:
            return self._path


    @property
    def mode(self):
        with self.image_lock:
            return self._mode


    @property
    def order(self):
        with self.image_lock:
            return self._order


    @property
    def width(self):
        with self.image_lock:
            return self._width


    @property
    def height(self):
        with self.image_lock:
            return self._height


    @property
    def n_images(self):
        with self.image_lock:
            return self._n_images


    @property
    def n_channels(self):
        with self.image_lock:
            return self._n_channels


    @property
    def n_frames(self):
        with self.image_lock:
            return self._n_frames


class RoiSet:
    ROI_TYPE_RAW = 'raw'
    ROI_TYPE_RECT = 'rect'

    def __init__(self, roi_arr, type_=ROI_TYPE_RECT):

        # Change ROI into index array
        if type_ == RoiSet.ROI_TYPE_RECT:
            self._roi_arr = roi_arr

        elif type_ == RoiSet.ROI_TYPE_RAW:
            self._roi_arr = roi_arr

        else:
            raise ValueError("Unknown ROI type: {}", type_, file=sys.stderr)

    def __iter__(self):
        return self._roi_arr.__iter__()

    def __getitem__(self, key):
        try:
            return self._roi_arr[key]
        except IndexError:
            return None
