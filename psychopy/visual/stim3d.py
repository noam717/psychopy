#!/usr/bin/env python
# -*- coding: utf-8 -*-

"""Classes for 3D stimuli."""

# Part of the PsychoPy library
# Copyright (C) 2002-2018 Jonathan Peirce (C) 2019 Open Science Tools Ltd.
# Distributed under the terms of the GNU General Public License (GPL).

from psychopy.visual.basevisual import ColorMixin
from psychopy.visual.helpers import setColor
import psychopy.tools.mathtools as mt
import psychopy.tools.gltools as gt
import psychopy.tools.arraytools as at
from psychopy.visual.shaders import vertPhongLighting, fragPhongLighting
from itertools import product
import os
from io import StringIO
from PIL import Image

import numpy as np

import pyglet.gl as GL

# Dictionary of material shaders. Keys for shaders are defined as (nLights,
# hasDiffuse).
_material_shaders_ = {}

# Generate shaders for materials. Create a separate shader for permutations of
# texture and lighting number.
MAX_LIGHTS = 8

# Create shader flags, these are used as keys to pick the appropriate shader
# for the given material and lighting configuration.
shaderFlags = []
for i in range(1, MAX_LIGHTS + 1):
    for j in product((True, False), repeat=1):
        shaderFlags.append((i, *j))

# Compile shaders based on generated flags.
for flag in shaderFlags:
    # Define GLSL preprocessor values to enable code paths for specific material
    # properties.
    srcDefs = {'MAX_LIGHTS': flag[0]}

    if flag[1]:  # has diffuse texture map
        srcDefs['DIFFUSE_TEXTURE'] = 1

    # embed #DEFINE statements in GLSL source code
    vertSrc = gt.embedShaderSourceDefs(vertPhongLighting, srcDefs)
    fragSrc = gt.embedShaderSourceDefs(fragPhongLighting, srcDefs)

    # build a shader program
    prog = gt.createProgramObjectARB()
    vertexShader = gt.compileShaderObjectARB(
        vertSrc, GL.GL_VERTEX_SHADER_ARB)
    fragmentShader = gt.compileShaderObjectARB(
        fragSrc, GL.GL_FRAGMENT_SHADER_ARB)

    gt.attachObjectARB(prog, vertexShader)
    gt.attachObjectARB(prog, fragmentShader)
    gt.linkProgramObjectARB(prog)
    gt.detachObjectARB(prog, vertexShader)
    gt.detachObjectARB(prog, fragmentShader)
    gt.deleteObjectARB(vertexShader)
    gt.deleteObjectARB(fragmentShader)

    # set the flag
    _material_shaders_[flag] = prog


class LightSource(object):
    """Class for representing a light source in a scene.

    Only point and directional lighting is supported by this object for now. The
    ambient color of the light source contributes to the scene ambient color
    defined by :py:attr:`~psychopy.visual.Window.ambientLight`.

    """
    def __init__(self,
                 win,
                 pos=(0., 0., 0.),
                 diffuseColor=(1., 1., 1.),
                 specularColor=(1., 1., 1.),
                 ambientColor=(0., 0., 0.),
                 colorSpace='rgb',
                 lightType='point',
                 kAttenuation=(1, 0, 0)):
        """
        Parameters
        ----------
        win : `~psychopy.visual.Window`
            Window associated with this light source.
        pos : array_like
            Position of the light source (x, y, z, w). If `w=1.0` the light will
            be a point source and `x`, `y`, and `z` is the position in the
            scene. If `w=0.0`, the light source will be directional and `x`,
            `y`, and `z` will define the vector pointing to the direction the
            light source is coming from. For instance, a vector of (0, 1, 0, 0)
            will indicate that a light source is coming from above.
        diffuseColor : array_like
            Diffuse light color.
        specularColor : array_like
            Specular light color.
        ambientColor : array_like
            Ambient light color.
        colorSpace : str
            Colorspace for `diffuse`, `specular`, and `ambient` colors.
        kAttenuation : array_like
            Values for the constant, linear, and quadratic terms of the lighting
            attenuation formula. Default is (1, 0, 0) which results in no
            attenuation.

        """
        self.win = win

        self._pos = np.zeros((4,), np.float32)
        self._diffuseColor = np.zeros((3,), np.float32)
        self._specularColor = np.zeros((3,), np.float32)
        self._ambientColor = np.zeros((3,), np.float32)

        # internal RGB values post colorspace conversion
        self._diffuseRGB = np.array((0., 0., 0., 1.), np.float32)
        self._specularRGB = np.array((0., 0., 0., 1.), np.float32)
        self._ambientRGB = np.array((0., 0., 0., 1.), np.float32)

        self.colorSpace = colorSpace
        self.diffuseColor = diffuseColor
        self.specularColor = specularColor
        self.ambientColor = ambientColor

        self._lightType = lightType
        self.pos = pos

        # attenuation factors
        self._kAttenuation = np.asarray(kAttenuation, np.float32)

    @property
    def pos(self):
        """Position of the light source in the scene in scene units."""
        return self._pos[:3]

    @pos.setter
    def pos(self, value):
        self._pos = np.zeros((4,), np.float32)
        self._pos[:3] = value

        if self._lightType == 'point':
            self._pos[3] = 1.0

    @property
    def lightType(self):
        """Type of light source, can be 'point' or 'directional'."""
        return self._pos[:3]

    @lightType.setter
    def lightType(self, value):
        self._lightType = value

        if self._lightType == 'point':
            self._pos[3] = 1.0
        elif self._lightType == 'directional':
            self._pos[3] = 0.0
        else:
            raise ValueError(
                "Unknown `lightType` specified, must be 'directional' or "
                "'point'.")


    @property
    def diffuseColor(self):
        """Diffuse color of the material."""
        return self._diffuseColor

    @diffuseColor.setter
    def diffuseColor(self, value):
        self._diffuseColor = np.asarray(value, np.float32)
        setColor(self, value, colorSpace=self.colorSpace, operation=None,
                 rgbAttrib='diffuseRGB', colorAttrib='diffuseColor',
                 colorSpaceAttrib='colorSpace')

    @property
    def diffuseRGB(self):
        """Diffuse color of the material."""
        return self._diffuseRGB[:3]

    @diffuseRGB.setter
    def diffuseRGB(self, value):
        # make sure the color we got is 32-bit float
        self._diffuseRGB = np.zeros((4,), np.float32)
        self._diffuseRGB[:3] = (value + 1) / 2.0
        self._diffuseRGB[3] = 1.0

    @property
    def specularColor(self):
        """Specular color of the material."""
        return self._specularColor

    @specularColor.setter
    def specularColor(self, value):
        self._specularColor = np.asarray(value, np.float32)
        setColor(self, value, colorSpace=self.colorSpace, operation=None,
                 rgbAttrib='specularRGB', colorAttrib='specularColor',
                 colorSpaceAttrib='colorSpace')

    @property
    def specularRGB(self):
        """Diffuse color of the material."""
        return self._specularRGB[:3]

    @specularRGB.setter
    def specularRGB(self, value):
        # make sure the color we got is 32-bit float
        self._specularRGB = np.zeros((4,), np.float32)
        self._specularRGB[:3] = (value + 1) / 2.0
        self._specularRGB[3] = 1.0

    @property
    def ambientColor(self):
        """Ambient color of the material."""
        return self._ambientColor

    @ambientColor.setter
    def ambientColor(self, value):
        self._ambientColor = np.asarray(value, np.float32)
        setColor(self, value, colorSpace=self.colorSpace, operation=None,
                 rgbAttrib='ambientRGB', colorAttrib='ambientColor',
                 colorSpaceAttrib='colorSpace')

    @property
    def ambientRGB(self):
        """Diffuse color of the material."""
        return self._ambientRGB[:3]

    @ambientRGB.setter
    def ambientRGB(self, value):
        # make sure the color we got is 32-bit float
        self._ambientRGB = np.zeros((4,), np.float32)
        self._ambientRGB[:3] = (value * + 1) / 2.0
        self._ambientRGB[3] = 1.0

    @property
    def kAttenuation(self):
        """Values for the constant, linear, and quadratic terms of the lighting
        attenuation formula.
        """
        return self._kAttenuation

    @kAttenuation.setter
    def kAttenuation(self, value):
        self._kAttenuation = np.asarray(value, np.float32)


class PhongMaterial(object):
    """Class representing a material using the Phong lighting model.

    This class stores material information to modify the appearance of drawn
    primitives with respect to lighting, such as color (diffuse, specular,
    ambient, and emission), shininess, and textures. Simple materials are
    intended to work with features supported by the fixed-function OpenGL
    pipeline.

    """
    def __init__(self,
                 win=None,
                 diffuseColor=(.5, .5, .5),
                 specularColor=(-1., -1., -1.),
                 ambientColor=(-1., -1., -1.),
                 emissionColor=(-1., -1., -1.),
                 shininess=10.0,
                 colorSpace='rgb',
                 diffuseTexture=None,
                 opacity=1.0,
                 contrast=1.0,
                 face='front',
                 useShaders=False):
        """
        Parameters
        ----------
        win : `~psychopy.visual.Window` or `None`
            Window this material is associated with, required for shaders and
            some color space conversions.
        diffuseColor : array_like
            Diffuse material color (r, g, b, a) with values between 0.0 and 1.0.
        specularColor : array_like
            Specular material color (r, g, b, a) with values between 0.0 and
            1.0.
        ambientColor : array_like
            Ambient material color (r, g, b, a) with values between 0.0 and 1.0.
        emissionColor : array_like
            Emission material color (r, g, b, a) with values between 0.0 and
            1.0.
        shininess : float
            Material shininess, usually ranges from 0.0 to 128.0.
        colorSpace : float
            Color space for `diffuseColor`, `specularColor`, `ambientColor`, and
            `emissionColor`.
        diffuseTexture : TexImage2D
        opacity : float
            Opacity of the material. Ranges from 0.0 to 1.0 where 1.0 is fully
            opaque.
        contrast : float
            Contrast of the material colors.
        face : str
            Face to apply material to. Values are `front`, `back` or `both`.
        textures : dict, optional
            Texture maps associated with this material. Textures are specified
            as a list. The index of textures in the list will be used to set
            the corresponding texture unit they are bound to.
        useShaders : bool
            Use per-pixel lighting when rendering this stimulus. By default,
            Blinn-Phong shading will be used.
        """
        self.win = win

        self._diffuseColor = np.zeros((3,), np.float32)
        self._specularColor = np.zeros((3,), np.float32)
        self._ambientColor = np.zeros((3,), np.float32)
        self._emissionColor = np.zeros((3,), np.float32)
        self._shininess = float(shininess)

        # internal RGB values post colorspace conversion
        self._diffuseRGB = np.array((0., 0., 0., 1.), np.float32)
        self._specularRGB = np.array((0., 0., 0., 1.), np.float32)
        self._ambientRGB = np.array((0., 0., 0., 1.), np.float32)
        self._emissionRGB = np.array((0., 0., 0., 1.), np.float32)

        # which faces to apply the material

        if face == 'front':
            self._face = GL.GL_FRONT
        elif face == 'back':
            self._face = GL.GL_BACK
        elif face == 'both':
            self._face = GL.GL_FRONT_AND_BACK
        else:
            raise ValueError("Invalid `face` specified, must be 'front', "
                             "'back' or 'both'.")

        self.colorSpace = colorSpace
        self.opacity = opacity
        self.contrast = contrast

        self.diffuseColor = diffuseColor
        self.specularColor = specularColor
        self.ambientColor = ambientColor
        self.emissionColor = emissionColor

        self._diffuseTexture = diffuseTexture
        self._normalTexture = None

        self._useTextures = False  # keeps track if textures are being used
        self._useShaders = useShaders

    @property
    def diffuseTexture(self):
        """Diffuse color of the material."""
        return self._diffuseTexture

    @diffuseTexture.setter
    def diffuseTexture(self, value):
        self._diffuseTexture = value

    @property
    def diffuseColor(self):
        """Diffuse color of the material."""
        return self._diffuseColor

    @diffuseColor.setter
    def diffuseColor(self, value):
        self._diffuseColor = np.asarray(value, np.float32)
        setColor(self, value, colorSpace=self.colorSpace, operation=None,
                 rgbAttrib='diffuseRGB', colorAttrib='diffuseColor',
                 colorSpaceAttrib='colorSpace')

    @property
    def diffuseRGB(self):
        """Diffuse color of the material."""
        return self._diffuseRGB[:3]

    @diffuseRGB.setter
    def diffuseRGB(self, value):
        # make sure the color we got is 32-bit float
        self._diffuseRGB = np.zeros((4,), np.float32)
        self._diffuseRGB[:3] = (value * self.contrast + 1) / 2.0
        self._diffuseRGB[3] = self.opacity

    @property
    def specularColor(self):
        """Specular color of the material."""
        return self._specularColor

    @specularColor.setter
    def specularColor(self, value):
        self._specularColor = np.asarray(value, np.float32)
        setColor(self, value, colorSpace=self.colorSpace, operation=None,
                 rgbAttrib='specularRGB', colorAttrib='specularColor',
                 colorSpaceAttrib='colorSpace')

    @property
    def specularRGB(self):
        """Diffuse color of the material."""
        return self._specularRGB[:3]

    @specularRGB.setter
    def specularRGB(self, value):
        # make sure the color we got is 32-bit float
        self._specularRGB = np.zeros((4,), np.float32)
        self._specularRGB[:3] = (value * self.contrast + 1) / 2.0
        self._specularRGB[3] = self.opacity

    @property
    def ambientColor(self):
        """Ambient color of the material."""
        return self._ambientColor

    @ambientColor.setter
    def ambientColor(self, value):
        self._ambientColor = np.asarray(value, np.float32)
        setColor(self, value, colorSpace=self.colorSpace, operation=None,
                 rgbAttrib='ambientRGB', colorAttrib='ambientColor',
                 colorSpaceAttrib='colorSpace')

    @property
    def ambientRGB(self):
        """Diffuse color of the material."""
        return self._ambientRGB[:3]

    @ambientRGB.setter
    def ambientRGB(self, value):
        # make sure the color we got is 32-bit float
        self._ambientRGB = np.zeros((4,), np.float32)
        self._ambientRGB[:3] = (value * self.contrast + 1) / 2.0
        self._ambientRGB[3] = self.opacity

    @property
    def emissionColor(self):
        """Emission color of the material."""
        return self._emissionColor

    @emissionColor.setter
    def emissionColor(self, value):
        self._emissionColor = np.asarray(value, np.float32)
        setColor(self, value, colorSpace=self.colorSpace, operation=None,
                 rgbAttrib='emissionRGB', colorAttrib='emissionColor',
                 colorSpaceAttrib='colorSpace')

    @property
    def emissionRGB(self):
        """Diffuse color of the material."""
        return self._emissionRGB[:3]

    @emissionRGB.setter
    def emissionRGB(self, value):
        # make sure the color we got is 32-bit float
        self._emissionRGB = np.zeros((4,), np.float32)
        self._emissionRGB[:3] = (value * self.contrast + 1) / 2.0
        self._emissionRGB[3] = self.opacity

    @property
    def shininess(self):
        return self._shininess

    @shininess.setter
    def shininess(self, value):
        self._shininess = float(value)



class RigidBodyPose(object):
    """Class for representing rigid body poses.

    This class is an abstract representation of a rigid body pose, where the
    position of the body in a scene is represented by a vector/coordinate and
    the orientation with a quaternion. Pose can be manipulated and interacted
    with using class methods and attributes. Rigid body poses assume a
    right-handed coordinate system (-Z is forward and +Y is up).

    Poses can be converted to 4x4 transformation matrices with `getModelMatrix`.
    One can use these matrices when rendering to transform the vertices of a
    model associated with the pose by passing them to OpenGL. Matrices are
    cached internally to avoid recomputing them if `pos` and `ori` attributes
    have not been updated.

    Operators `*` and `~` can be used on `RigidBodyPose` objects to combine and
    invert poses. For instance, you can multiply (`*`) poses to get a new pose
    which is the combination of both orientations and translations by::

        newPose = rb1 * rb2

    Likewise, a pose can be inverted by using the `~` operator::

        invPose = ~rb

    Multiplying a pose by its inverse will result in an identity pose with no
    translation and default orientation where `pos=[0, 0, 0]` and
    `ori=[0, 0, 0, 1]`::

        identityPose = ~rb * rb

    """
    def __init__(self, pos=(0., 0., 0.), ori=(0., 0., 0., 1.)):
        """
        Parameters
        ----------
        pos : array_like
            Position vector `[x, y, z]` for the origin of the rigid body.
        ori : array_like
            Orientation quaternion `[x, y, z, w]` where `x`, `y`, `z` are
            imaginary and `w` is real.

        """
        self._pos = np.ascontiguousarray(pos, dtype=np.float32)
        self._ori = np.ascontiguousarray(ori, dtype=np.float32)

        self._modelMatrix = mt.posOriToMatrix(
            self._pos, self._ori, dtype=np.float32)

        # computed only if needed
        self._invModelMatrix = np.zeros(4, dtype=np.float32, order='C')

        # compute matrices only if `pos` and `ori` attributes have been updated
        self._matrixNeedsUpdate = False
        self._invMatrixNeedsUpdate = False

    @property
    def pos(self):
        """Position vector (X, Y, Z)."""
        return self._pos

    @pos.setter
    def pos(self, value):
        self._pos = np.ascontiguousarray(value, dtype=np.float32)
        self._matrixNeedsUpdate = self._invMatrixNeedsUpdate = True

    @property
    def ori(self):
        """Orientation quaternion (X, Y, Z, W)."""
        return self._ori

    @ori.setter
    def ori(self, value):
        self._ori = np.ascontiguousarray(value, dtype=np.float32)
        self._matrixNeedsUpdate = self._invMatrixNeedsUpdate = True

    def __mul__(self, other):
        """Multiply two poses, combining them to get a new pose."""
        return RigidBodyPose(self._pos + other.pos,
                             mt.multQuat(self._ori, other.ori))

    def isEqual(self, other):
        """Check if poses have similar orientation and position.

        Parameters
        ----------
        other : `RigidBodyPose`
            Other pose to compare.

        Returns
        -------
        bool
            Returns `True` is poses are effectively equal.

        """
        return np.isclose(self._pos, other.pos) and \
            np.isclose(self._ori, other.ori)

    def getOriAxisAngle(self, degrees=True):
        """Get the axis and angle of rotation for the rigid body. Converts the
        orientation defined by the `ori` quaternion to and axis-angle
        representation.

        Parameters
        ----------
        degrees : bool, optional
            Specify ``True`` if `angle` is in degrees, or else it will be
            treated as radians. Default is ``True``.

        Returns
        -------
        tuple
            Axis [rx, ry, rz] and angle.

        """
        return mt.quatToAxisAngle(self._ori, degrees)

    def setOriAxisAngle(self, axis, angle, degrees=True):
        """Set the orientation of the rigid body using an `axis` and
        `angle`. This sets the quaternion at `ori`.

        Parameters
        ----------
        axis : array_like
            Axis of rotation [rx, ry, rz].
        angle : float
            Angle of rotation.
        degrees : bool, optional
            Specify ``True`` if `angle` is in degrees, or else it will be
            treated as radians. Default is ``True``.

        """
        self.ori = mt.quatFromAxisAngle(axis, angle, degrees)

    @property
    def modelMatrix(self):
        """Pose as a 4x4 model matrix (read-only)."""
        if not self._matrixNeedsUpdate:
            return self._modelMatrix
        else:
            return self.getModelMatrix()

    @property
    def inverseModelMatrix(self):
        """Inverse of the pose as a 4x4 model matrix (read-only)."""
        if not self._invModelMatrix:
            return self._invModelMatrix
        else:
            return self.getModelMatrix(inverse=True)

    def getModelMatrix(self, inverse=False, out=None):
        """Get the present rigid body transformation as a 4x4 matrix.

        Matrices are computed only if the `pos` and `ori` attributes have been
        updated since the last call to `getModelMatrix`. The returned matrix is
        an `ndarray` and row-major.

        Parameters
        ----------
        inverse : bool, optional
            Return the inverse of the model matrix.
        out : ndarray or None
            Optional 4x4 array to write values to. Values written are computed
            using 32-bit float precision regardless of the data type of `out`.

        Returns
        -------
        ndarray
            4x4 transformation matrix.

        Examples
        --------
        Using a rigid body pose to transform something in OpenGL::

            rb = RigidBodyPose((0, 0, -2))  # 2 meters away from origin

            # Use `array2pointer` from `psychopy.tools.arraytools` to convert
            # array to something OpenGL accepts.
            mv = array2pointer(rb.modelMatrix)

            # use the matrix to transform the scene
            glMatrixMode(GL_MODELVIEW)
            glPushMatrix()
            glLoadIdentity()
            glMultTransposeMatrixf(mv)

            # draw the thing here ...

            glPopMatrix()

        """
        if self._matrixNeedsUpdate:
            self._modelMatrix = mt.posOriToMatrix(
                self._pos, self._ori, out=self._modelMatrix)

            self._matrixNeedsUpdate = False

        # only update and return the inverse matrix if requested
        if inverse:
            if self._invMatrixNeedsUpdate:
                self._invModelMatrix = mt.invertMatrix(
                    self._modelMatrix, out=self._invModelMatrix)
                self._invMatrixNeedsUpdate = False

            if out is not None:
                out[:, :] = self._invModelMatrix[:, :]

            return self._invModelMatrix  # return the inverse

        if out is not None:
            out[:, :] = self._modelMatrix[:, :]

        return self._modelMatrix

    def transform(self, v, out=None):
        """Transform a vector using this pose.

        Parameters
        ----------
        v : array_like
            Vector to transform [x, y, z].
        out : ndarray or None, optional
            Optional array to write values to. Must have the same shape as
            `v`.

        Returns
        -------
        ndarray
            Transformed points.

        """
        return mt.transform(self._pos, self._ori, points=v, out=out)

    def __invert__(self):
        """Operator `~` to invert the pose. Returns a `RigidBodyPose` object."""
        return RigidBodyPose(
            -self._pos, mt.invertQuat(self._ori, dtype=np.float32))

    def invert(self):
        """Invert this pose.
        """
        self._ori = mt.invertQuat(self._ori, dtype=np.float32)
        self._pos *= -1.0

    def inverted(self):
        """Get a pose which is the inverse of this one.

        Returns
        -------
        RigidBodyPose
            This pose inverted.

        """
        return RigidBodyPose(
            -self._pos, mt.invertQuat(self._ori, dtype=np.float32))

    def distanceTo(self, v):
        """Get the distance to a pose or point in scene units.

        Parameters
        ----------
        v : RigidBodyPose or array_like
            Pose or point [x, y, z] to compute distance to.

        Returns
        -------
        float
            Distance to `v` from this pose's origin.

        """
        if hasattr(v, 'pos'):
            targetPos = v.pos
        else:
            targetPos = np.asarray(v[:3])

        return np.sqrt(np.sum(np.square(targetPos - self.pos)))


class BaseRigidBodyStim(ColorMixin):
    """Base class for rigid body 3D stimuli.

    This class handles the pose of a rigid body 3D stimulus. Poses are
    represented by a `RigidBodyClass` object accessed via `thePose` attribute.

    Any class the implements `pos` and `ori` attributes can be used in place of
    a `RigidBodyPose` instance for `thePose`. This common interface allows for
    custom classes which handle 3D transformations to be used for stimulus
    transformations (eg. `LibOVRPose` in PsychXR can be used instead of
    `RigidBodyPose` which supports more VR specific features).

    """
    def __init__(self,
                 win,
                 pos=(0., 0., 0.),
                 ori=(0., 0., 0., 1.),
                 color=(0.0, 0.0, 0.0),
                 colorSpace='rgb',
                 contrast=1.0,
                 opacity=1.0,
                 useShaders=False,
                 name='',
                 autoLog=True):
        """
        Parameters
        ----------
        win : `~psychopy.visual.Window`
            Window this stimulus is associated with. Stimuli cannot be shared
            across windows unless they share the same context.
        pos : array_like
            Position vector `[x, y, z]` for the origin of the rigid body.
        ori : array_like
            Orientation quaternion `[x, y, z, w]` where `x`, `y`, `z` are
            imaginary and `w` is real.

        """
        self.win = win
        self.name = name
        self.autoLog = autoLog

        self.colorSpace = colorSpace
        self.contrast = contrast
        self.opacity = opacity

        super(BaseRigidBodyStim, self).__init__()
        self.color = color

        self._thePose = RigidBodyPose(pos, ori)
        self._useShaders = useShaders
        self.material = None

        self._vao = None

    @property
    def thePose(self):
        """The pose of the rigid body. This is a class which has `pos` and `ori`
        attributes."""
        return self._thePose

    @thePose.setter
    def thePose(self, value):
        if hasattr(value, 'pos') and hasattr(value, 'ori'):
            self._thePose = value
        else:
            raise AttributeError(
                'Class set to `thePose` does not implement `pos` or `ori`.')

    @property
    def pos(self):
        """Position vector (X, Y, Z)."""
        return self.thePose.pos

    @pos.setter
    def pos(self, value):
        self.thePose.pos = value

    def getPos(self):
        return self.thePose.pos

    def setPos(self, pos):
        self.thePose.pos = pos

    @property
    def ori(self):
        """Orientation quaternion (X, Y, Z, W)."""
        return self.thePose.ori

    @ori.setter
    def ori(self, value):
        self.thePose.ori = value

    def getOri(self):
        return self.thePose.ori

    def setOri(self, ori):
        self.thePose.ori = ori

    def getOriAxisAngle(self, degrees=True):
        """Get the axis and angle of rotation for the 3D stimulus. Converts the
        orientation defined by the `ori` quaternion to and axis-angle
        representation.

        Parameters
        ----------
        degrees : bool, optional
            Specify ``True`` if `angle` is in degrees, or else it will be
            treated as radians. Default is ``True``.

        Returns
        -------
        tuple
            Axis `[rx, ry, rz]` and angle.

        """
        return self.thePose.getOriAxisAngle(degrees)

    def setOriAxisAngle(self, axis, angle, degrees=True):
        """Set the orientation of the 3D stimulus using an `axis` and
        `angle`. This sets the quaternion at `ori`.

        Parameters
        ----------
        axis : array_like
            Axis of rotation [rx, ry, rz].
        angle : float
            Angle of rotation.
        degrees : bool, optional
            Specify ``True`` if `angle` is in degrees, or else it will be
            treated as radians. Default is ``True``.

        """
        self.thePose.setOriAxisAngle(axis, angle, degrees)

    def draw(self):
        raise NotImplementedError(
            '3D stimulus classes must override visual.BaseRigidBodyStim.draw')

    def _createVAO(self, vertices, textureCoords, normals, faces):
        """Create a vertex array object for handling vertex attribute data.
        """
        # upload to buffers
        vertexVBO = gt.createVBO(vertices)
        texCoordVBO = gt.createVBO(textureCoords)
        normalsVBO = gt.createVBO(normals)

        # create an index buffer with faces
        indexBuffer = gt.createVBO(
            faces.flatten(),
            target=GL.GL_ELEMENT_ARRAY_BUFFER,
            dataType=GL.GL_UNSIGNED_INT)

        return gt.createVAO({0: vertexVBO, 8: texCoordVBO, 2: normalsVBO},
            indexBuffer=indexBuffer)

    def draw(self, win=None):
        """Draw the stimulus.

        This should work for stimuli using a single VAO and material. More
        complex stimuli with multiple materials should override this method to
        correctly handle that case.

        Parameters
        ----------
        win : `~psychopy.visual.Window`
            Window this stimulus is associated with. Stimuli cannot be shared
            across windows unless they share the same context.

        """
        if win is None:
            win = self.win

        # nop if there is no VAO to draw
        if self._vao is None:
            return

        win.draw3d = True

        # apply transformation to mesh
        GL.glPushMatrix()
        GL.glLoadTransposeMatrixf(at.array2pointer(self.thePose.modelMatrix))

        if self.material is not None:  # has a material, use it
            if self._useShaders:
                nLights = len(self.win.lights)
                shaderKey = (nLights, self.material._useTextures)
                gt.useMaterial(self.material)
                gt.useProgram(_material_shaders_[shaderKey])
                gt.drawVAO(self._vao, GL.GL_TRIANGLES)
                gt.useProgram(0)
                gt.clearMaterial(self.material)
            else:
                gt.useMaterial(self.material)
                gt.drawVAO(self._vao, GL.GL_TRIANGLES)
                gt.clearMaterial(self.material)
        else:  # doesn't have a material, use class colors
            r, g, b = self._getDesiredRGB(
                self.rgb, self.colorSpace, self.contrast)

            if self._useShaders:
                nLights = len(self.win.lights)
                shaderKey = (nLights, False, False)
                gt.useProgram(_material_shaders_[shaderKey])
                color = np.ctypeslib.as_ctypes(
                    np.array((r, g, b, self.opacity), np.float32))
                # pass values to OpenGL as material
                GL.glMaterialfv(GL.GL_FRONT, GL.GL_DIFFUSE, color)
                GL.glMaterialfv(GL.GL_FRONT, GL.GL_AMBIENT, color)

                gt.drawVAO(self._vao, GL.GL_TRIANGLES)

                gt.useProgram(0)
            else:
                # material tracks color
                GL.glEnable(GL.GL_COLOR_MATERIAL)  # enable color tracking
                GL.glDisable(GL.GL_TEXTURE_2D)
                GL.glColorMaterial(GL.GL_FRONT, GL.GL_AMBIENT_AND_DIFFUSE)
                # 'rgb' is created and set when color is set
                GL.glColor4f(r, g, b, self.opacity)

                # draw the shape
                gt.drawVAO(self._vao, GL.GL_TRIANGLES)
                GL.glDisable(GL.GL_COLOR_MATERIAL)  # enable color tracking

        GL.glPopMatrix()

        win.draw3d = False


class SphereStim(BaseRigidBodyStim):
    """Class for drawing a UV sphere.

    The resolution of the sphere mesh can be controlled by setting `sectors`
    and `stacks` which controls the number of latitudinal and longitudinal
    subdivisions, respectively. The radius of the sphere is defined by setting
    `radius` expressed in scene units (meters if using a perspective
    projection).

    Calling the `draw` method will render the sphere to the current buffer. The
    render target (FBO or back buffer) must have a depth buffer attached to it
    for the object to be rendered correctly. Shading is used if the current
    window has light sources defined and lighting is enabled (by setting
    `useLights=True` before drawing the stimulus).

    Examples
    --------
    Creating a red sphere 1.5 meters away from the viewer with radius 0.25::

        redSphere = SphereStim(win,
                               pos=(0., 0., -1.5),
                               radius=0.25,
                               color=(1, 0, 0))

    """
    def __init__(self,
                 win,
                 radius=0.5,
                 subdiv=(32, 32),
                 flipFaces=False,
                 pos=(0., 0., 0.),
                 ori=(0., 0., 0., 1.),
                 useMaterial=None,
                 useShaders=False,
                 color=(0., 0., 0.),
                 colorSpace='rgb',
                 contrast=1.0,
                 opacity=1.0,
                 name='',
                 autoLog=True):
        """
        Parameters
        ----------
        win : `~psychopy.visual.Window`
            Window this stimulus is associated with. Stimuli cannot be shared
            across windows unless they share the same context.
        radius : float
            Radius of the sphere in scene units.
        subdiv : array_like
            Number of latitudinal and longitudinal subdivisions `(lat, long)`
            for the sphere mesh. The greater the number, the smoother the sphere
            will appear.
        flipFaces : bool, optional
            If `True`, normals and face windings will be set to point inward
            towards the center of the sphere. Texture coordinates will remain
            the same. Default is `False`.
        pos : array_like
            Position vector `[x, y, z]` for the origin of the rigid body.
        ori : array_like
            Orientation quaternion `[x, y, z, w]` where `x`, `y`, `z` are
            imaginary and `w` is real. If you prefer specifying rotations in
            axis-angle format, call `setOriAxisAngle` after initialization.
        useMaterial : SimpleMaterial, optional
            Material to use. The material can be configured by accessing the
            `material` attribute after initialization. If not material is
            specified, the diffuse and ambient color of the shape will be set
            by `color`.
        color : array_like
            Diffuse and ambient color of the stimulus if `useMaterial` is not
            specified. Values are with respect to `colorSpace`.
        colorSpace : str
            Colorspace of `color` to use.
        contrast : float
            Contrast of the stimulus, value modulates the `color`.
        opacity : float
            Opacity of the stimulus ranging from 0.0 to 1.0. Note that
            transparent objects look best when rendered from farthest to
            nearest.
        name : str
            Name of this object for logging purposes.
        autoLog : bool
            Enable automatic logging on attribute changes.

        """
        super(SphereStim, self).__init__(win,
                                         pos=pos,
                                         ori=ori,
                                         color=color,
                                         colorSpace=colorSpace,
                                         contrast=contrast,
                                         opacity=opacity,
                                         useShaders=useShaders,
                                         name=name,
                                         autoLog=autoLog)

        # create a vertex array object for drawing
        self._vao = self._createVAO(
            *gt.createUVSphere(sectors=subdiv[0],
                               stacks=subdiv[1],
                               radius=radius,
                               flipFaces=flipFaces))

        self.material = useMaterial
        self._useShaders = useShaders


class BoxStim(BaseRigidBodyStim):
    """Class for drawing 3D boxes.

    Draws a rectangular box with dimensions specified by `size` (length, width,
    height) in scene units.

    Calling the `draw` method will render the box to the current buffer. The
    render target (FBO or back buffer) must have a depth buffer attached to it
    for the object to be rendered correctly. Shading is used if the current
    window has light sources defined and lighting is enabled (by setting
    `useLights=True` before drawing the stimulus).

    """
    def __init__(self,
                 win,
                 size=(.5, .5, .5),
                 pos=(0., 0., 0.),
                 ori=(0., 0., 0., 1.),
                 flipFaces=False,
                 useMaterial=None,
                 color=(0., 0., 0.),
                 colorSpace='rgb',
                 contrast=1.0,
                 opacity=1.0,
                 useShaders=True,
                 name='',
                 autoLog=True):
        """
        Parameters
        ----------
        win : `~psychopy.visual.Window`
            Window this stimulus is associated with. Stimuli cannot be shared
            across windows unless they share the same context.
        size : tuple or float
            Dimensions of the mesh. If a single value is specified, the box will
            be a cube. Provide a tuple of floats to specify the width, length,
            and height of the box (eg. `size=(0.2, 1.3, 2.1)`) in scene units.
        pos : array_like
            Position vector `[x, y, z]` for the origin of the rigid body.
        ori : array_like
            Orientation quaternion `[x, y, z, w]` where `x`, `y`, `z` are
            imaginary and `w` is real. If you prefer specifying rotations in
            axis-angle format, call `setOriAxisAngle` after initialization.
        flipFaces : bool, optional
            If `True`, normals and face windings will be set to point inward
            towards the center of the box. Texture coordinates will remain the
            same. Default is `False`.
        useMaterial : SimpleMaterial, optional
            Material to use. The material can be configured by accessing the
            `material` attribute after initialization. If not material is
            specified, the diffuse and ambient color of the shape will track the
            current color specified by `glColor`.
            color : array_like
            Diffuse and ambient color of the stimulus if `useMaterial` is not
            specified. Values are with respect to `colorSpace`.
        colorSpace : str
            Colorspace of `color` to use.
        contrast : float
            Contrast of the stimulus, value modulates the `color`.
        opacity : float
            Opacity of the stimulus ranging from 0.0 to 1.0. Note that
            transparent objects look best when rendered from farthest to
            nearest.
        name : str
            Name of this object for logging purposes.
        autoLog : bool
            Enable automatic logging on attribute changes.

        """
        super(BoxStim, self).__init__(
            win,
            pos=pos,
            ori=ori,
            color=color,
            colorSpace=colorSpace,
            contrast=contrast,
            opacity=opacity,
            useShaders=useShaders,
            name=name,
            autoLog=autoLog)

        # create a vertex array object for drawing
        self._vao = self._createVAO(*gt.createBox(size, flipFaces))

        self.setColor(color, colorSpace=self.colorSpace, log=False)
        self.material = useMaterial


class PlaneStim(BaseRigidBodyStim):
    """Class for drawing planes.

    Draws a plane with dimensions specified by `size` (length, width) in scene
    units.

    Calling the `draw` method will render the plane to the current buffer. The
    render target (FBO or back buffer) must have a depth buffer attached to it
    for the object to be rendered correctly. Shading is used if the current
    window has light sources defined and lighting is enabled (by setting
    `useLights=True` before drawing the stimulus).

    """
    def __init__(self,
                 win,
                 size=(.5, .5),
                 pos=(0., 0., 0.),
                 ori=(0., 0., 0., 1.),
                 useMaterial=None,
                 useShaders=True,
                 color=(0., 0., 0.),
                 colorSpace='rgb',
                 contrast=1.0,
                 opacity=1.0,
                 name='',
                 autoLog=True):
        """
        Parameters
        ----------
        win : `~psychopy.visual.Window`
            Window this stimulus is associated with. Stimuli cannot be shared
            across windows unless they share the same context.
        size : tuple or float
            Dimensions of the mesh. If a single value is specified, the plane
            will be a square. Provide a tuple of floats to specify the width and
            length of the plane (eg. `size=(0.2, 1.3)`).
        pos : array_like
            Position vector `[x, y, z]` for the origin of the rigid body.
        ori : array_like
            Orientation quaternion `[x, y, z, w]` where `x`, `y`, `z` are
            imaginary and `w` is real. If you prefer specifying rotations in
            axis-angle format, call `setOriAxisAngle` after initialization. By
            default, the plane is oriented with normal facing the +Z axis of the
            scene.
        useMaterial : SimpleMaterial, optional
            Material to use. The material can be configured by accessing the
            `material` attribute after initialization. If not material is
            specified, the diffuse and ambient color of the shape will track the
            current color specified by `glColor`.

        """
        super(PlaneStim, self).__init__(
            win,
            pos=pos,
            ori=ori,
            color=color,
            colorSpace=colorSpace,
            contrast=contrast,
            opacity=opacity,
            useShaders=useShaders,
            name=name,
            autoLog=autoLog)

        # create a vertex array object for drawing
        self._vao = self._createVAO(*gt.createPlane(size))

        self.setColor(color, colorSpace=self.colorSpace, log=False)
        self.material = useMaterial


class ObjMeshStim(BaseRigidBodyStim):
    """Class for loading and presenting 3D stimuli in the Wavefront OBJ format.

    Calling the `draw` method will render the mesh to the current buffer. The
    render target (FBO or back buffer) must have a depth buffer attached to it
    for the object to be rendered correctly. Shading is used if the current
    window has light sources defined and lighting is enabled (by setting
    `useLights=True` before drawing the stimulus).

    Vertex positions, texture coordinates, and normals are loaded and packed
    into a single vertex buffer object (VBO). Vertex array objects (VAO) are
    created for each material with an index buffer referencing vertices assigned
    that material in the VBO. For maximum performance, keep the number of
    materials per object as low as possible, as switching between VAOs has some
    overhead.

    Material attributes are read from the material library file (*.MTL)
    associated with the *.OBJ file. This file will be automatically searched for
    and read during loading. Afterwards you can edit material properties by
    accessing the data structure of the `materials` attribute.

    Keep in mind that OBJ shapes are rigid bodies, the mesh itself cannot be
    deformed during runtime. However, meshes can be positioned and rotated as
    desired by manipulating the `RigidBodyPose` instance accessed through the
    `thePose` attribute.

    Warnings
    --------
        Loading an *.OBJ file is a slow process, be sure to do this outside
        of any time-critical routines!

    Examples
    --------
    Loading an *.OBJ file from a disk location::

        myObjStim = ObjMeshStim(win, '/path/to/file/model.obj')

    """
    def __init__(self,
                 win,
                 objFile,
                 pos=(0, 0, 0),
                 ori=(0, 0, 0, 1),
                 useMaterial=None,
                 useShaders=True):
        """
        Parameters
        ----------
        win : `~psychopy.visual.Window`
            Window this stimulus is associated with. Stimuli cannot be shared
            across windows unless they share the same context.
        size : tuple or float
            Dimensions of the mesh. If a single value is specified, the plane
            will be a square. Provide a tuple of floats to specify the width and
            length of the box (eg. `size=(0.2, 1.3)`).
        pos : array_like
            Position vector `[x, y, z]` for the origin of the rigid body.
        ori : array_like
            Orientation quaternion `[x, y, z, w]` where `x`, `y`, `z` are
            imaginary and `w` is real. If you prefer specifying rotations in
            axis-angle format, call `setOriAxisAngle` after initialization. By
            default, the plane is oriented with normal facing the +Z axis of the
            scene.
        useMaterial : SimpleMaterial, optional
            Material to use. The material can be configured by accessing the
            `material` attribute after initialization. If no material is
            specified, materials will be loaded from the associated MTL file. If
            there is no MTL file, a default material will be used for all
            meshes. This material can be edited via the `material` attribute
            after initialization.
        useShaders : bool
            Use shaders when rendering.

        """
        super(ObjMeshStim, self).__init__(win, pos=pos, ori=ori)

        objModel = gt.loadObjFile(objFile)

        if useMaterial is None:
            if objModel.mtlFile is not None:
                self.material = self._loadMtlLib(objModel.mtlFile)
            else:
                self.material = PhongMaterial(self.win)
        else:
            self.material = useMaterial

        # load vertex data into an interleaved VBO
        buffers = np.ascontiguousarray(
            np.hstack((objModel.vertexPos,
                       objModel.texCoords,
                       objModel.normals)),
            dtype=np.float32)

        # upload to buffer
        vertexAttr = gt.createVBO(buffers)

        # load vertex data into VAOs
        self._vao = {}  # dictionary for VAOs
        # for each material create a VAO
        # keys are material names, values are index buffers
        for material, faces in objModel.faces.items():
            # convert index buffer to VAO
            indexBuffer = \
                gt.createVBO(
                    faces.flatten(),  # flatten face index for element array
                    target=GL.GL_ELEMENT_ARRAY_BUFFER,
                    dataType=GL.GL_UNSIGNED_INT)

            # see `setVertexAttribPointer` for more information about attribute
            # pointer indices
            self._vao[material] = gt.createVAO(
                {GL.GL_VERTEX_ARRAY: (vertexAttr, 3),
                 GL.GL_TEXTURE_COORD_ARRAY: (vertexAttr, 2, 3),
                 GL.GL_NORMAL_ARRAY: (vertexAttr, 3, 5, True)},
                indexBuffer=indexBuffer, legacy=True)

        self._useShaders = useShaders

    def _loadMtlLib(self, mtlFile):
        """Load a material library associated with the OBJ file. This is usually
        called by the constructor for this class.

        Parameters
        ----------
        mtlFile : str
            Path to MTL file.

        """
        with open(mtlFile, 'r') as mtl:
            mtlBuffer = StringIO(mtl.read())

        foundMaterials = {}
        foundTextures = {}
        thisMaterial = 0
        for line in mtlBuffer.readlines():
            line = line.strip()
            if line.startswith('newmtl '):  # new material
                thisMaterial = line[7:]
                foundMaterials[thisMaterial] = PhongMaterial(self.win)
            elif line.startswith('Ns '):  # specular exponent
                foundMaterials[thisMaterial].shininess = line[3:]
            elif line.startswith('Ks '):  # specular color
                specularColor = np.asarray(list(map(float, line[3:].split(' '))))
                specularColor = 2.0 * specularColor - 1
                foundMaterials[thisMaterial].specularColor = specularColor
            elif line.startswith('Kd '):  # diffuse color
                diffuseColor = np.asarray(list(map(float, line[3:].split(' '))))
                diffuseColor = 2.0 * diffuseColor - 1
                foundMaterials[thisMaterial].diffuseColor = diffuseColor
            elif line.startswith('Ka '):  # ambient color
                ambientColor = np.asarray(list(map(float, line[3:].split(' '))))
                ambientColor = 2.0 * ambientColor - 1
                foundMaterials[thisMaterial].ambientColor = ambientColor
            elif line.startswith('map_Kd '):  # diffuse color map
                # load a diffuse texture from file
                textureName = line[7:]
                if textureName not in foundTextures.keys():
                    im = Image.open(
                        os.path.join(os.path.split(mtlFile)[0], textureName))
                    im = im.transpose(Image.FLIP_TOP_BOTTOM)
                    im = im.convert("RGBA")
                    pixelData = np.array(im).ctypes
                    width = pixelData.shape[1]
                    height = pixelData.shape[0]
                    foundTextures[textureName] = gt.createTexImage2D(
                        width,
                        height,
                        internalFormat=GL.GL_RGBA,
                        pixelFormat=GL.GL_RGBA,
                        dataType=GL.GL_UNSIGNED_BYTE,
                        data=pixelData,
                        unpackAlignment=1,
                        texParams={GL.GL_TEXTURE_MAG_FILTER: GL.GL_LINEAR,
                                   GL.GL_TEXTURE_MIN_FILTER: GL.GL_LINEAR})
                foundMaterials[thisMaterial].diffuseTexture = \
                    foundTextures[textureName]

        return foundMaterials

    def draw(self, win=None):
        """Draw the mesh.

        Parameters
        ----------
        win : `~psychopy.visual.Window`
            Window this stimulus is associated with. Stimuli cannot be shared
            across windows unless they share the same context.

        """
        if win is None:
            win = self.win

        win.draw3d = True

        GL.glPushMatrix()
        GL.glLoadTransposeMatrixf(at.array2pointer(self.thePose.modelMatrix))

        # iterate over materials, draw associated VAOs
        if self.material is not None:
            mtlIndex = 0
            nMaterials = len(self.material)
            nLights = len(self.win.lights)

            for materialName, materialDesc in self.material.items():
                shaderKey = (nLights, materialDesc._useTextures)
                gt.useMaterial(materialDesc)
                if self._useShaders:
                    gt.useProgram(_material_shaders_[shaderKey])

                gt.drawVAO(self._vao[materialName], GL.GL_TRIANGLES)
                mtlIndex += 1

                # clear the material when done
                if mtlIndex == nMaterials:
                    if self._useShaders:
                        gt.useProgram(0)
                    gt.clearMaterial(materialDesc)

        else:
            for materialName, _ in self.material.items():
                gt.drawVAO(self._vao, GL.GL_TRIANGLES)

        GL.glPopMatrix()

        win.draw3d = False

        if win is None:
            win = self.win

        win.draw3d = True