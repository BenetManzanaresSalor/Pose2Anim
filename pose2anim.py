import os
import json
import math
from string import Template


############################################ Pose2Anim ############################################
class Pose2Anim:
	DEFAULT_BODY_ORIENTATION = 90
	DEFAULT_MIN_CONFIDENCE = 0.6
	DEFAULT_MIN_TREMBLING_FREQ = 7
	DEFAULT_MLF_MAX_ERROR_RATIO = 0.1
	DEFAULT_MAX_KEYS_PER_SEC = 0
	DEFAULT_FRAME_RATE = 30

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

	def __init__(self, in_path, out_path, openpose_path, bone_settings, **kwargs):
		self.set_execution_settings(in_path, out_path, openpose_path, bone_settings)

		body_orientation = kwargs.get("body_orientation", self.DEFAULT_BODY_ORIENTATION)
		min_confidence = kwargs.get("min_confidence", self.DEFAULT_MIN_CONFIDENCE)
		min_trembling_freq = kwargs.get("min_trembling_freq", self.DEFAULT_MIN_TREMBLING_FREQ)
		mlf_max_error_ratio = kwargs.get("mlf_max_error_ratio", self.DEFAULT_MLF_MAX_ERROR_RATIO)
		max_keys_per_sec = kwargs.get("max_keys_per_sec", self.DEFAULT_MAX_KEYS_PER_SEC)
		self.set_process_settings(body_orientation, min_confidence,
		                          min_trembling_freq, mlf_max_error_ratio,
		                          max_keys_per_sec)

	def set_execution_settings(self, in_path, out_path, openpose_path, bones_settings):
		self.in_path = in_path
		self.out_path = out_path
		self.openpose_path = openpose_path
		self.bones_settings = bones_settings

		self.in_file_name = os.path.splitext(os.path.basename(in_path))[0]
		self.out_poses_path = os.path.join(out_path, self.in_file_name)
		self.out_poses_path = os.path.normpath(self.out_poses_path)

		self.frame_rate = self.DEFAULT_FRAME_RATE    # TODO : Autodetect from input video

	def set_process_settings(self, body_orientation=DEFAULT_BODY_ORIENTATION,
	                         min_confidence=DEFAULT_MIN_CONFIDENCE,
	                         min_trembling_freq=DEFAULT_MIN_TREMBLING_FREQ,
	                         mlf_max_error_ratio=DEFAULT_MLF_MAX_ERROR_RATIO,
	                         max_keys_per_sec=DEFAULT_MAX_KEYS_PER_SEC):
		self.body_orientation = body_orientation

		if min_confidence < 0 or min_confidence > 1:
			raise AttributeError("min_confidence must be in the range [0, 1]")
		else:
			self.min_confidence = min_confidence

		if min_trembling_freq < 0:
			raise AttributeError("min_trembling_freq must be greater than or equal to 0")
		else:
			self.min_trembling_freq = min_trembling_freq
			self.max_trembling_period = 1 / self.min_trembling_freq if min_trembling_freq > 0 else 0

		self.mlf_max_error_ratio = mlf_max_error_ratio
		self.max_keys_per_sec = max_keys_per_sec

	###################### Detect poses ######################
	def detect_poses(self, in_path, out_path):
		current_path = os.getcwd()
		os.chdir(self.openpose_path)
		self.exe_openpose(in_path, out_path)
		os.chdir(current_path)

	def exe_openpose(self, in_path, out_path):
		command = f"start bin/OpenPoseDemo.exe --keypoint_scale 3 --video {in_path} --write_json {out_path}"
		stream = os.popen(command)
		stream.read()

	###################### Read poses ######################
	def read_poses(self, poses_path, bones_settings, person_idx=0):
		bones_values = [[] for _ in range(len(bones_settings))]
		time = 0
		duration = 0
		num_frames = 0
		first_correct_frame = -1
		time_per_frame = 1 / self.frame_rate

		# Read bones values
		file_names = os.listdir(poses_path)
		for file_name in file_names:
			if file_name.endswith(".json"):
				file_path = os.path.join(poses_path, file_name)
				with open(file_path) as frame_file:
					frame_dict = json.load(frame_file)
					time = (num_frames - max(0, first_correct_frame)) * time_per_frame
					contains_data = self.get_bones_values(frame_dict, time, bones_settings, bones_values, person_idx)
					if contains_data:
						if first_correct_frame == -1:
							first_correct_frame = num_frames
						else:
							duration = time
					num_frames += 1

		return bones_values, duration

	def get_bones_values(self, frame_dict, time, bones_settings, bones_values, person_idx=0):
		contains_data = False

		people = frame_dict["people"]
		if len(people) > person_idx:
			keypoints = people[person_idx]["pose_keypoints_2d"]
			for i, bone_setting in enumerate(bones_settings):
				# Manage parent value
				parent_idx = bone_setting[2]
				needs_parent = parent_idx != -1
				has_parent = False
				if needs_parent:
					parent_bone = bones_values[parent_idx]
					has_parent = len(parent_bone) > 0
					if has_parent:
						parent_values = parent_bone[-1]
						has_parent = parent_values[0] == time  # Last frame is the current

				is_correct = has_parent or not needs_parent
				if is_correct:
					ini = self.get_kp(keypoints, bone_setting[0])
					end = self.get_kp(keypoints, bone_setting[1])

					if ini and end:
						offset = self.kp_sub(end, ini)
						angle = math.atan2(offset[1], offset[0])
						angle = math.degrees(angle) - self.body_orientation
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
		for bone_idx in range(len(bones_values)):
			bone_keys = bones_values[bone_idx]
			num_bone_keys = len(bone_keys)
			if num_bone_keys != 0:

				# Remove high frequency trembling
				if self.min_trembling_freq > 0:
					bones_values[bone_idx] = bone_keys = self.remove_trembling(bone_keys)

				# Fit the line to reduce redundancy and noise
				if self.mlf_max_error_ratio > 0:
					bones_values[bone_idx] = bone_keys = self.multiple_line_fitting(bone_keys)

				# Compute averages if is needed
				if self.max_keys_per_sec > 0:
					num_bone_keys = len(bone_keys)
					last_time = bone_keys[0][0]
					last_key_idx = 0
					key_idx = 0
					num_keys_in_second = 0
					new_keypoint_idx = 0

					while key_idx < num_bone_keys:
						time = bone_keys[key_idx][0]
						elapsed_time = time - last_time
						is_last = key_idx == (num_bone_keys - 1)
						num_keys_in_second += 1
						# Compute the average if a second has passed or num keys == MAX_KEYS_PER_SECOND or is_last
						if elapsed_time > 1 or num_keys_in_second >= self.max_keys_per_sec or is_last:
							keys_for_average = bone_keys[last_key_idx:key_idx + 1]
							bone_keys[new_keypoint_idx] = self.bone_keys_average(keys_for_average, is_last)
							last_time = time
							num_keys_in_second = 0
							last_key_idx = key_idx + 1
							new_keypoint_idx += 1

						key_idx += 1

					# Update bone keys only catching the averages values
					bones_values[bone_idx] = bone_keys = bone_keys[:new_keypoint_idx]

				# Compute slopes
				for key_idx, key in enumerate(bone_keys):
					slope = self.compute_slope(bone_keys, key_idx)
					key.append(slope)

		return bones_values

	def multiple_line_fitting(self, bone_keys):
		num_bone_keys = len(bone_keys)
		new_bone_keys = [bone_keys[0], bone_keys[-1]]
		max_error_idx = 0

		# Search max and min values
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
		max_smooth_error = values_range * self.mlf_max_error_ratio

		# While any keypoint exceed the MAX_SMOOTH_ERROR
		while max_error_idx != -1:
			key_idx = 1
			max_error_idx = -1
			max_error_val = max_smooth_error
			max_error_kp = None
			# Search the maximum-error keypoint
			while key_idx < num_bone_keys - 1:
				keypoint = bone_keys[key_idx]
				interpolated_value, corresponding_idx = self.mlf_interpolate(new_bone_keys, keypoint[0])
				error = abs(interpolated_value - keypoint[1])
				if error >= max_error_val:
					max_error_idx = corresponding_idx
					max_error_val = error
					max_error_kp = keypoint
				key_idx += 1

			if max_error_idx != -1:
				new_bone_keys.insert(max_error_idx, max_error_kp)

		return new_bone_keys

	def mlf_interpolate(self, bone_keys, time, corresponding_idx=-1):
		# Search corresponding index if is needed
		if corresponding_idx == -1:
			corresponding_idx = 0
			while bone_keys[corresponding_idx][0] < time:
				corresponding_idx += 1

		previous_idx = max(corresponding_idx - 1, 0)
		previous_kp = bone_keys[previous_idx]
		next_idx = corresponding_idx
		next_kp = bone_keys[next_idx]
		slope = (next_kp[1] - previous_kp[1]) / (next_kp[0] - previous_kp[0])
		time_offset = time - previous_kp[0]
		value = previous_kp[1] + time_offset * slope

		return value, corresponding_idx

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

	def bone_keys_average(self, bone_keys, is_last=False):
		average = [0, 0]

		# Set time and check if is_first or is_last
		is_first = bone_keys[0][0] == 0
		compute_time_average = not (is_first or is_last)
		if is_first:
			average[0] = 0
		elif is_last:
			average[0] = bone_keys[-1][0]

		# Sum values
		for time, value in bone_keys:
			if compute_time_average:
				average[0] = average[0] + time
			average[1] = average[1] + value

		# Compute averages
		num_values = float(len(bone_keys))
		if compute_time_average:
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
	def write_anim(self, bones_values, bones_settings, duration, file_path):
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

				curve_tmpl_values['PATH'] = bones_settings[bone_idx][3]
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

	########### Complete execution ###########
	def run(self, person_idx=0):
		self.out_anim_path = os.path.join(self.out_path, f"{self.in_file_name}{person_idx}.anim")
		self.out_anim_path = os.path.normpath(self.out_anim_path)

		if not os.path.exists(self.out_poses_path):
			self.detect_poses(self.in_path, self.out_poses_path)

		bones_values, duration = self.read_poses(self.out_poses_path, self.bones_settings, person_idx)
		bones_values = self.process_bones_values(bones_values)
		self.write_anim(bones_values, self.bones_settings, duration, self.out_anim_path)

		return bones_values


############################################ MAIN ############################################
def main():
	# Execution settings
	in_path = "E:/PROYECTOS/Pose2Anim/Input/Nerea.mp4"
	out_path = "E:/PROYECTOS/Pose2Anim/Pose2AnimUnity/Assets/Animations"
	openpose_path = "openpose"
	bones_settings = [(8, 1, -1, 'bone_1/bone_2'),
	                  (1, 0, 0, 'bone_1/bone_2/bone_3'),
	                  (2, 3, 0, 'bone_1/bone_2/bone_6'),
	                  (3, 4, 2, 'bone_1/bone_2/bone_6/bone_7'),
	                  (5, 6, 0, 'bone_1/bone_2/bone_4'),
	                  (6, 7, 4, 'bone_1/bone_2/bone_4/bone_5'),
	                  (9, 10, 0, 'bone_1/bone_8'),
	                  (10, 11, 6, 'bone_1/bone_8/bone_9'),
	                  (12, 13, 0, 'bone_1/bone_10'),
	                  (13, 14, 8, 'bone_1/bone_10/bone_11')]

	# Process settings
	body_orientation = 90
	min_confidence = 0.6
	min_trembling_frequency = 7
	mlf_max_error_ratio = 0.1
	max_keys_per_second = 0

	pose2anim = Pose2Anim(in_path, out_path, openpose_path, bones_settings, body_orientation=body_orientation,
	                      min_confidence=min_confidence, min_trembling_freq=min_trembling_frequency,
	                      mlf_max_error_ratio=mlf_max_error_ratio, max_keys_per_sec=max_keys_per_second)
	pose2anim.run()


if __name__ == "__main__":
	main()
