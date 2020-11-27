import os
import subprocess
from json import load as json_load
from math import atan2, degrees
from string import Template
from cv2 import VideoCapture, CAP_PROP_FPS



############################################ Pose2Anim ############################################
class Pose2Anim:
	###################### Constants ######################
	DEFAULT_BODY_ORIENTATION = 90
	DEFAULT_MIN_CONFIDENCE = 0.6
	DEFAULT_MIN_TREMBLING_FREQ = 7
	DEFAULT_MLF_MAX_ERROR_RATIO = 0.1
	DEFAULT_AVG_KEYS_PER_SEC = 0
	OPENPOSE_RELATIVE_EXE_PATH = os.path.normpath("bin/OpenPoseDemo.exe")
	NUM_BONE_DEF_VALUES = 4

	ANIM_FILE_TEMPLATE = '''%YAML 1.1
%TAG !u! tag:unity3d.com,2011:
--- !u!74 &7400000
AnimationClip:
  m_ObjectHideFlags: 0
  m_CorrespondingSourceObject: {fileID: 0}
  m_PrefabInstance: {fileID: 0}
  m_PrefabAsset: {fileID: 0}
  m_Name: $NAME
  serializedVersion: 6
  m_Legacy: 0
  m_Compressed: 0
  m_UseHighQualityCurve: 1
  m_RotationCurves: []
  m_CompressedRotationCurves: []
  m_EulerCurves:
$EULER_CURVES  m_PositionCurves: []
  m_ScaleCurves: []
  m_FloatCurves: []
  m_PPtrCurves: []
  m_SampleRate: 60
  m_WrapMode: 0
  m_Bounds:
    m_Center: {x: 0, y: 0, z: 0}
    m_Extent: {x: 0, y: 0, z: 0}
  m_ClipBindingConstant:
    genericBindings:
    - serializedVersion: 2
      path: 134607859
      attribute: 4
      script: {fileID: 0}
      typeID: 4
      customType: 4
      isPPtrCurve: 0
    pptrCurveMapping: []
  m_AnimationClipSettings:
    serializedVersion: 2
    m_AdditiveReferencePoseClip: {fileID: 0}
    m_AdditiveReferencePoseTime: 0
    m_StartTime: 0
    m_StopTime: $DURATION
    m_OrientationOffsetY: 0
    m_Level: 0
    m_CycleOffset: 0
    m_HasAdditiveReferencePose: 0
    m_LoopTime: 1
    m_LoopBlend: 0
    m_LoopBlendOrientation: 0
    m_LoopBlendPositionY: 0
    m_LoopBlendPositionXZ: 0
    m_KeepOriginalOrientation: 0
    m_KeepOriginalPositionY: 1
    m_KeepOriginalPositionXZ: 0
    m_HeightFromFeet: 0
    m_Mirror: 0
  m_EditorCurves:
$EDITOR_CURVES  m_EulerEditorCurves: []
  m_HasGenericRootTransform: 0
  m_HasMotionFloatCurves: 0
  m_Events: []
'''
	EULER_CURVE_TEMPLATE = '''  - curve:
      serializedVersion: 2
      m_Curve:
$CURVE      m_PreInfinity: 2    
      m_PostInfinity: 2
      m_RotationOrder: 4
    path: $PATH
'''
	EULER_CURVE_KEY_TEMPLATE = '''      - serializedVersion: 3
        time: $TIME
        value: $VALUE
        inSlope: $SLOPE
        outSlope: $SLOPE
        tangentMode: 0
        weightedMode: 0
        inWeight: {x: 0, y: 0, z: 0.5}
        outWeight: {x: 0, y: 0, z: 0.5}
'''
	EDITOR_CURVE_TEMPLATE = '''  - curve:
      serializedVersion: 2
      m_Curve:
$CURVE      m_PreInfinity: 2
      m_PostInfinity: 2
      m_RotationOrder: 4
    attribute: $ATTR
    path: $PATH
    classID: 4
    script: {fileID: 0}
'''
	EDITOR_CURVE_KEY_TEMPLATE = '''      - serializedVersion: 3
        time: $TIME
        value: $VALUE
        inSlope: $SLOPE
        outSlope: $SLOPE
        tangentMode: 0
        weightedMode: 0
        inWeight: 0.5
        outWeight: 0.5
'''

	###################### External use ######################
	def __init__(self, **kwargs):
		# Set default settings
		self.video_path = None
		self.video_name = None
		self.frame_rate = None
		self.time_per_frame = None
		self.anim_path = None
		self.poses_path = None
		self.openpose_path = None
		self.bones_defs = None
		self.body_orientation = self.DEFAULT_BODY_ORIENTATION
		self.min_confidence = self.DEFAULT_MIN_CONFIDENCE
		self.min_trembling_freq = self.DEFAULT_MIN_TREMBLING_FREQ
		self.max_trembling_period = 1 / self.DEFAULT_MIN_TREMBLING_FREQ if self.DEFAULT_MIN_TREMBLING_FREQ > 0 else 0
		self.mlf_max_error_ratio = self.DEFAULT_MLF_MAX_ERROR_RATIO
		self.avg_keys_per_sec = self.DEFAULT_AVG_KEYS_PER_SEC

		# Set the arguments settings
		self.set_settings(**kwargs)

	def set_settings(self, **kwargs):
		# If has any setting
		if len(kwargs) > 0:
			video_path = kwargs.get("video_path", None)
			anim_path = kwargs.get("anim_path", None)
			openpose_path = kwargs.get("openpose_path", None)
			bones_defs = kwargs.get("bones_defs", None)
			body_orientation = kwargs.get("body_orientation", None)
			min_confidence = kwargs.get("min_confidence", None)
			min_trembling_freq = kwargs.get("min_trembling_freq", None)
			mlf_max_error_ratio = kwargs.get("mlf_max_error_ratio", None)
			avg_keys_per_sec = kwargs.get("avg_keys_per_sec", None)

			if video_path is not None:
				video_path = os.path.normpath(video_path)
				if not os.path.exists(video_path):
					raise AssertionError(f"video_path {video_path} does not exist")

				self.video_path = video_path
				self.video_name = os.path.splitext(os.path.basename(self.video_path))[0]
				video = VideoCapture(self.video_path)
				if not video.isOpened():
					raise AssertionError(f"video_path {video_path} does not contain a video")

				self.frame_rate = video.get(CAP_PROP_FPS)
				self.time_per_frame = 1 / self.frame_rate
				video.release()

				if self.anim_path is not None:
					self.poses_path = os.path.join(self.anim_path, self.video_name)

			if anim_path is not None:
				anim_path = os.path.normpath(anim_path)
				if not os.path.exists(anim_path):
					raise AssertionError(f"anim_path {anim_path} does not exist")

				self.anim_path = anim_path

				if self.video_name is not None:
					self.poses_path = os.path.join(self.anim_path, self.video_name)

			if openpose_path is not None:
				openpose_path = os.path.normpath(openpose_path)
				if not os.path.exists(openpose_path):
					raise AssertionError(f"openpose_path {openpose_path} does not exist")

				openpose_exe_path = os.path.join(openpose_path, self.OPENPOSE_RELATIVE_EXE_PATH)
				if not os.path.exists(openpose_exe_path):
					raise AssertionError(
						f"openpose_path {openpose_path} does not contain {self.OPENPOSE_RELATIVE_EXE_PATH}")

				self.openpose_path = openpose_path

			if bones_defs is not None:
				bones_defs = self.check_and_sort_bones_defs(bones_defs)
				self.bones_defs = bones_defs

			if body_orientation is not None:
				self.body_orientation = body_orientation % 360

			if min_confidence is not None:
				if min_confidence < 0 or min_confidence > 1:
					raise AssertionError("min_confidence must be in the range [0, 1]")
				self.min_confidence = min_confidence

			if min_trembling_freq is not None:
				if min_trembling_freq < 0:
					raise AssertionError("min_trembling_freq must be greater than or equal to 0")
				self.min_trembling_freq = min_trembling_freq
				self.max_trembling_period = 1 / min_trembling_freq if min_trembling_freq > 0 else 0

			if mlf_max_error_ratio is not None:
				if mlf_max_error_ratio < 0 or min_confidence > 1:
					raise AssertionError("mlf_max_error_ratio must be in the range [0, 1]")
				self.mlf_max_error_ratio = mlf_max_error_ratio

			if avg_keys_per_sec is not None:
				if avg_keys_per_sec < 0:
					raise AssertionError("avg_keys_per_sec must be greater than or equal to 0")
				self.avg_keys_per_sec = avg_keys_per_sec

	def run(self, person_idx=0, **kwargs):
		self.set_settings(**kwargs)
		self.check_if_can_run()

		self.out_anim_path = os.path.join(self.anim_path, f"{self.video_name}{person_idx}.anim")
		self.out_anim_path = os.path.normpath(self.out_anim_path)

		if not os.path.exists(self.poses_path):
			self.detect_poses(self.video_path, self.poses_path)

		bones_values, duration = self.read_poses(self.poses_path, self.bones_defs, person_idx)
		bones_values = self.process_bones_values(bones_values)
		self.write_anim(bones_values, self.bones_defs, duration, self.out_anim_path)

		return bones_values

	###################### Error detection ######################
	def check_and_sort_bones_defs(self, bones_defs):
		if not isinstance(bones_defs, list) or len(bones_defs) == 0:
			raise AssertionError("bones_defs must be a not-empty list, one element per bone")
		else:
			idx = 0
			num_bones = len(bones_defs)
			is_sorted = True
			while idx < num_bones:
				bone_def = bones_defs[idx]
				if len(bone_def) < self.NUM_BONE_DEF_VALUES:
					raise AssertionError(
						f"Bone in position {idx} of bones_defs has less than {self.NUM_BONE_DEF_VALUES} values\n {bone_def}")
				parent_idx = bone_def[2]
				if parent_idx == idx:
					raise AssertionError(
						f"Bone in position {idx} of bones_defs has himself as parent \n {self.bones_defs}")
				# If the bone_def is positioned before its parent, solve the problem
				elif parent_idx >= 0 and idx < parent_idx:
					if is_sorted:
						is_sorted = False
						bones_defs = bones_defs.copy()  # Copy the list before sort, to avoid modification of the original

					# Move the bone_def to a correct position
					new_bone_idx = parent_idx
					self.bones_defs.insert(new_bone_idx, self.bones_defs.pop(idx))
					bone_def[2] -= 1  # Now the parent is just before

					# Update affected parents indexes of bones_defs
					upd_idx = idx
					while upd_idx < num_bones:
						if upd_idx != new_bone_idx:
							upd_bone = self.bones_defs[upd_idx]
							upd_parent_idx = upd_bone[2]
							# If the parent index is between the movement positions, needs to be changed
							if idx <= upd_parent_idx <= new_bone_idx:
								# If it's a child of the moved
								if upd_parent_idx == idx:
									upd_parent_idx = new_bone_idx
								# If the parent is before the moved
								else:
									upd_parent_idx -= 1

								upd_bone[2] = upd_parent_idx

						upd_idx += 1

					idx -= 1  # Compensate the movement
				idx += 1

		return bones_defs

	def check_if_can_run(self):
		message = " must be assigned before run. " + \
		          "Add it as keyword argument at run, set_setting or constructor methods."

		if self.video_path is None:
			raise AssertionError("video_path" + message)
		if self.anim_path is None:
			raise AssertionError("anim_path" + message)
		if self.openpose_path is None:
			raise AssertionError("openpose_path" + message)
		if self.bones_defs is None:
			raise AssertionError("bones_defs" + message)

	###################### Detect poses ######################
	def detect_poses(self, in_path, out_path):
		current_path = os.getcwd()
		os.chdir(self.openpose_path)
		try:
			self.exe_openpose(in_path, out_path)
		except Exception as exc:
			raise Exception(f"Problem executing OpenPose: {exc}", exc)
		finally:
			os.chdir(current_path)

	def exe_openpose(self, in_path, out_path):
		command = f"{self.OPENPOSE_RELATIVE_EXE_PATH} --keypoint_scale 3 --video {in_path} --write_json {out_path}"
		subprocess.run(command, shell=True, check=True)

	###################### Read poses ######################
	def read_poses(self, poses_path, bones_defs, person_idx=0):
		bones_values = [[] for _ in range(len(bones_defs))]
		time = 0
		duration = 0
		num_frames = 0
		first_correct_frame = -1

		# Read bones values
		file_names = os.listdir(poses_path)
		for file_name in file_names:
			if file_name.endswith(".json"):
				file_path = os.path.join(poses_path, file_name)
				with open(file_path) as frame_file:
					frame_dict = json_load(frame_file)
					time = (num_frames - max(0, first_correct_frame)) * self.time_per_frame
					contains_data = self.get_bones_values(frame_dict, time, bones_defs, bones_values, person_idx)
					if contains_data:
						if first_correct_frame == -1:
							first_correct_frame = num_frames
						else:
							duration = time
					num_frames += 1

		return bones_values, duration

	def get_bones_values(self, frame_dict, time, bones_defs, bones_values, person_idx):
		contains_data = False

		people = frame_dict["people"]
		if len(people) > person_idx:
			keypoints = people[person_idx]["pose_keypoints_2d"]
			for i, bone_def in enumerate(bones_defs):
				# Manage parent value
				parent_idx = bone_def[2]
				needs_parent = parent_idx != -1
				has_parent = False
				parent_values = None
				if needs_parent:
					parent_bone = bones_values[parent_idx]
					has_parent = len(parent_bone) > 0
					if has_parent:
						parent_values = parent_bone[-1]
						has_parent = parent_values[0] == time  # Last frame is the current

				is_correct = has_parent or not needs_parent
				if is_correct:
					ini = self.get_kp(keypoints, bone_def[0])
					end = self.get_kp(keypoints, bone_def[1])

					if ini and end:
						offset = self.kp_sub(end, ini)
						angle = atan2(offset[1], offset[0])
						angle = degrees(angle) - self.body_orientation
						if has_parent:
							angle -= parent_values[1]
						angle = angle % 360

						# Use the more similar angle to the previous
						if len(bones_values[i]) > 0:
							previous_angle = bones_values[i][-1][1]
							possible_angles = [angle + 360, angle - 360]
							min_diff = abs(angle - previous_angle)
							for possible_angle in possible_angles:
								diff = abs(possible_angle - previous_angle)
								if diff < min_diff:
									min_diff = diff
									angle = possible_angle

						bones_values[i].append([time, angle])

				if is_correct and not contains_data:
					contains_data = True

		return contains_data

	def get_kp(self, keypoints, idx):
		kp = None

		if idx % 1 == 0:
			ini = idx * 3
			val = keypoints[ini: ini + 3]

			if val[2] >= self.min_confidence:
				kp = val
				kp[1] = 1 - kp[1]
		else:
			a = self.get_kp(keypoints, int(idx))
			b = self.get_kp(keypoints, int(idx + 1))
			if a and b:
				kp = self.kp_average(a, b)

		return kp

	def kp_average(self, a, b):
		return [(a[0] + b[0]) / 2, (a[1] + b[1]) / 2]

	def kp_sub(self, a, b):
		return [a[0] - b[0], a[1] - b[1]]

	########### Process bones values ###########
	def process_bones_values(self, bones_values):
		total_time = 0
		num_execs = 0
		num_keys = 0
		for bone_idx in range(len(bones_values)):
			bone_keys = bones_values[bone_idx]
			num_bone_keys = len(bone_keys)
			if num_bone_keys != 0:
				# Remove high frequency trembling
				if self.min_trembling_freq > 0:
					bones_values[bone_idx] = bone_keys = self.remove_trembling(bone_keys)

				# Fit the line to reduce redundancy and noise
				if self.mlf_max_error_ratio > 0:
					num_execs += 1
					num_keys += len(bone_keys)
					bones_values[bone_idx] = bone_keys = self.multi_line_fitting(bone_keys)

				# Compute averages if is needed
				if self.avg_keys_per_sec > 0:
					bones_values[bone_idx] = bone_keys = self.check_avg_keys_per_sec(bone_keys)

				# Compute slopes
				for key_idx, key in enumerate(bone_keys):
					slope = self.compute_slope(bone_keys, key_idx)
					key.append(slope)

		return bones_values

	def multi_line_fitting(self, bone_keys):
		new_bone_keys = [bone_keys[0], bone_keys[-1]]
		new_bone_keys_idxs = [0, len(bone_keys) - 1]
		num_bone_keys = len(bone_keys)

		# Search max and min values to compute the maximum error
		max_value = max(bone_keys[0][1], bone_keys[-1][1])
		min_value = min(bone_keys[0][1], bone_keys[-1][1])
		key_idx = 1
		while key_idx < num_bone_keys - 1:
			keypoint = bone_keys[key_idx]
			if keypoint[1] > max_value:
				max_value = keypoint[1]
			elif keypoint[1] < min_value:
				min_value = keypoint[1]
			key_idx += 1

		values_range = max_value - min_value
		max_error = values_range * self.mlf_max_error_ratio

		# While any keypoint exceeds the maximum error
		max_error_keys = []
		ini_section_idx = 1
		mid_section_idx = num_bone_keys - 2
		end_section_idx = mid_section_idx
		has_errors = True
		while has_errors:
			# Search the maximum-error keypoints of the two parts of the section
			first_section = bone_keys[ini_section_idx:mid_section_idx]
			error = self.mlf_search_max_error(first_section, max_error, new_bone_keys)
			if error[0] is not None:
				error[0] += ini_section_idx  # Add the section offset
				max_error_keys.append(error)
			second_section = bone_keys[mid_section_idx:end_section_idx]
			error = self.mlf_search_max_error(second_section, max_error, new_bone_keys)
			if error[0] is not None:
				error[0] += mid_section_idx  # Add the section offset
				max_error_keys.append(error)

			# If has some error
			if len(max_error_keys) != 0:
				# Get the maximum-error keypoint
				max_error_val = -1
				max_error_idx = -1
				max_error_kp = None
				corresponding_idx = -1
				max_error_idx_to_remove = - 1
				for idx, error in enumerate(max_error_keys):
					error_idx, error_kp, error_val = error
					if error_val > max_error_val:
						max_error_idx = error_idx
						max_error_kp = error_kp
						max_error_val = error_val
						corresponding_idx = self.mlf_get_corresponding_idx(max_error_kp[0], new_bone_keys)
						max_error_idx_to_remove = idx

				# Add the new keypoint
				new_bone_keys.insert(corresponding_idx, max_error_kp)
				new_bone_keys_idxs.insert(corresponding_idx, max_error_idx)
				max_error_keys.pop(max_error_idx_to_remove)

				# Set the new sections indexes
				ini_section_idx = new_bone_keys_idxs[corresponding_idx - 1] + 1
				mid_section_idx = max_error_idx
				end_section_idx = new_bone_keys_idxs[corresponding_idx + 1]
			else:
				has_errors = False

		return new_bone_keys

	def mlf_search_max_error(self, bone_keys, max_error, new_bone_keys):
		max_error_idx = None
		max_error_kp = None
		max_error_val = max_error

		for idx, keypoint in enumerate(bone_keys):
			interpolated_value, corresponding_idx = self.mlf_interpolate(keypoint[0], new_bone_keys)
			error = abs(interpolated_value - keypoint[1])
			if error >= max_error_val:
				max_error_idx = idx
				max_error_kp = keypoint
				max_error_val = error

		return [max_error_idx, max_error_kp, max_error_val]

	def mlf_interpolate(self, time, new_bone_keys, corresponding_idx=-1):
		# Search corresponding index if is needed
		if corresponding_idx == -1:
			corresponding_idx = self.mlf_get_corresponding_idx(time, new_bone_keys)
			while new_bone_keys[corresponding_idx][0] < time:
				corresponding_idx += 1

		previous_idx = max(corresponding_idx - 1, 0)
		previous_kp = new_bone_keys[previous_idx]
		next_idx = corresponding_idx
		next_kp = new_bone_keys[next_idx]
		slope = (next_kp[1] - previous_kp[1]) / (next_kp[0] - previous_kp[0])
		time_offset = time - previous_kp[0]
		value = previous_kp[1] + time_offset * slope

		return value, corresponding_idx

	def mlf_get_corresponding_idx(self, time, new_bone_keys):
		corresponding_idx = 0
		while time > new_bone_keys[corresponding_idx][0]:
			corresponding_idx += 1

		return corresponding_idx

	def remove_trembling(self, bone_keys):
		num_bone_keys = len(bone_keys)
		new_bone_keys = [bone_keys[0]]

		key_idx = 1
		previous_kp = bone_keys[0]
		keypoint = bone_keys[key_idx]
		ini_wave_idx = -1
		while key_idx < num_bone_keys - 1:
			next_kp = bone_keys[key_idx + 1]
			has_wave_period = (next_kp[0] - previous_kp[
				0]) <= self.max_trembling_period  # Time smaller than the maximum trembling period
			has_wave_values = (keypoint[1] - previous_kp[1] > 0) != (
					next_kp[1] - keypoint[1] > 0)  # It's a wave if the slope changes
			is_trembling_wave = has_wave_period and has_wave_values
			if is_trembling_wave:
				# If is the start of a trembling wave
				if ini_wave_idx == -1:
					ini_wave_idx = key_idx
			else:
				# If is end of the wave, ignore the trembling
				if ini_wave_idx != -1:
					ini_wave_idx = -1

				# Always add if it don't belongs to a trembling wave
				new_bone_keys.append(keypoint)

			# Advance to next
			previous_kp = keypoint
			keypoint = next_kp
			key_idx += 1

		# Always add last keypoint
		new_bone_keys.append(bone_keys[-1])

		return new_bone_keys

	def check_avg_keys_per_sec(self, bone_keys):
		num_bone_keys = len(bone_keys)
		ini_second_time = bone_keys[1][0]
		ini_second_key_idx = 1
		key_idx = 2
		new_keypoint_idx = 1

		while key_idx < num_bone_keys - 1:
			time = bone_keys[key_idx][0]
			elapsed_time = time - ini_second_time
			is_penultimate = key_idx == (num_bone_keys - 2)

			if is_penultimate:
				key_idx += 1  # Needed to include it in averages computation

			# If a second passed
			if elapsed_time > 1 or is_penultimate:
				keys_count = key_idx - ini_second_key_idx
				# If the key count is less than or equal to the desired
				if keys_count <= self.avg_keys_per_sec:
					new_keypoint_idx += keys_count  # Don't modify these keys
				# If the key count is grater than the desired
				else:
					num_keys_to_avg = keys_count // self.avg_keys_per_sec
					ini = ini_second_key_idx
					end = ini + num_keys_to_avg
					# Compute the averages
					for i in range(0, self.avg_keys_per_sec - 1):
						keys_for_average = bone_keys[ini:end]
						bone_keys[new_keypoint_idx] = self.bone_keys_average(keys_for_average)
						new_keypoint_idx += 1
						ini = end
						end = ini + num_keys_to_avg

					# Add the last average
					keys_for_average = bone_keys[ini:key_idx]
					bone_keys[new_keypoint_idx] = self.bone_keys_average(keys_for_average)
					new_keypoint_idx += 1

				ini_second_time = time
				ini_second_key_idx = key_idx

			key_idx += 1

		# Add the last keypoint
		bone_keys[new_keypoint_idx] = bone_keys[-1]
		new_keypoint_idx += 1

		return bone_keys[:new_keypoint_idx]

	def bone_keys_average(self, bone_keys):
		average = [0, 0]

		# Sum values
		for time, value in bone_keys:
			average[0] = average[0] + time
			average[1] = average[1] + value

		# Compute averages
		num_values = float(len(bone_keys))
		average[0] /= num_values
		average[1] /= num_values

		return average

	def compute_slope(self, bone_keys, key_idx):
		slope = 0

		if key_idx != 0 and key_idx != len(bone_keys) - 1:
			previous_kp = bone_keys[key_idx - 1]
			next_kp = bone_keys[key_idx + 1]
			slope = (next_kp[1] - previous_kp[1]) / (next_kp[0] - previous_kp[0])

		return slope

	########### Write animation ###########
	def write_anim(self, bones_values, bones_defs, duration, file_path):
		euler_curve_tmpl = Template(self.EULER_CURVE_TEMPLATE)
		euler_curves_str = ''
		euler_keys_tmpl = Template(self.EULER_CURVE_KEY_TEMPLATE)
		euler_keys_str = ''
		editor_curve_tmpl = Template(self.EDITOR_CURVE_TEMPLATE)
		editor_curves_str = ''
		editor_keys_tmpl = Template(self.EDITOR_CURVE_KEY_TEMPLATE)
		editor_keys_str = ''
		curve_tmpl_values = {'CURVE': '', 'PATH': '', 'ATTR': 'localEulerAnglesRaw.z'}
		key_tmpl_values = {'TIME': 0, 'VALUE': 0, 'SLOPE': 0}

		for bone_idx, bone_values in enumerate(bones_values):
			if len(bone_values) != 0:
				for time, value, slope in bone_values:
					key_tmpl_values['TIME'] = '%.2f' % time
					key_tmpl_values['VALUE'] = '{x: 0, y: 0, z: ' + value.__str__() + '}'
					key_tmpl_values['SLOPE'] = '{x: 0, y: 0, z: ' + slope.__str__() + '}'
					euler_keys_str += euler_keys_tmpl.substitute(key_tmpl_values)
					key_tmpl_values['VALUE'] = value
					key_tmpl_values['SLOPE'] = slope
					editor_keys_str += editor_keys_tmpl.substitute(key_tmpl_values)

				curve_tmpl_values['PATH'] = bones_defs[bone_idx][3]
				curve_tmpl_values['CURVE'] = euler_keys_str
				euler_curves_str += euler_curve_tmpl.substitute(curve_tmpl_values)
				curve_tmpl_values['CURVE'] = editor_keys_str
				editor_curves_str += editor_curve_tmpl.substitute(curve_tmpl_values)
				euler_keys_str = ''
				editor_curves_str = ''

		file_tmpl = Template(self.ANIM_FILE_TEMPLATE)
		anim_name = os.path.splitext(os.path.basename(file_path))[0]
		tmpl_values = {'NAME': anim_name,
		               'EULER_CURVES': euler_curves_str,
		               'DURATION': duration,
		               'EDITOR_CURVES': editor_curves_str,
		               'ATTR': 'localEulerAnglesRaw.z'}
		file_content = file_tmpl.substitute(tmpl_values)

		os.makedirs(os.path.dirname(file_path), exist_ok=True)
		with open(file_path, "w") as out_file:
			out_file.write(file_content)


############################################ MAIN ############################################
def main():
	# Execution settings
	video_path = "../Input/Body.mp4"
	anim_path = "../Pose2AnimUnity/Assets/Animations"
	openpose_path = "../openpose"
	bones_defs = [[8, 1, -1, 'bone_1/bone_2'],
	              [1, 0, 0, 'bone_1/bone_2/bone_3'],
	              [5, 6, 0, 'bone_1/bone_2/bone_4'],
	              [6, 7, 2, 'bone_1/bone_2/bone_4/bone_5'],
	              [2, 3, 0, 'bone_1/bone_2/bone_6'],
	              [3, 4, 4, 'bone_1/bone_2/bone_6/bone_7'],
	              [9, 10, 0, 'bone_1/bone_8'],
	              [10, 11, 6, 'bone_1/bone_8/bone_9'],
	              [12, 13, 0, 'bone_1/bone_10'],
	              [13, 14, 8, 'bone_1/bone_10/bone_11']]

	# Settings
	body_orientation = 90
	min_confidence = 0.6
	min_trembling_frequency = 7
	mlf_max_error_ratio = 0.1
	avg_keys_per_second = 0

	pose2anim = Pose2Anim(video_path=video_path, anim_path=anim_path, openpose_path=openpose_path,
	                      bones_defs=bones_defs, body_orientation=body_orientation,
	                      min_confidence=min_confidence, min_trembling_freq=min_trembling_frequency,
	                      mlf_max_error_ratio=mlf_max_error_ratio, avg_keys_per_sec=avg_keys_per_second)
	pose2anim.run()


if __name__ == "__main__":
	main()
