#!/usr/bin/env python3
import numpy as np
from scipy import signal
from fastdtw import fastdtw
from scipy.spatial.distance import euclidean
import matplotlib.pyplot as plt
import multiprocessing
import rospy
from std_msgs.msg import Float64MultiArray, String
from datetime import datetime
from pytz import timezone
import time
from quori_exercises.msg import ExerciseJointAngles

class ExerciseEval:

    def __init__(self, replay, feedback_controller):
        self.replay = replay
        self.flag = False

        if not self.replay:
            #Initialize the subscribers
            self.pose_sub = rospy.Subscriber("joint_angles", ExerciseJointAngles, self.pose_callback, queue_size=10)

        self.threshold1 = [1500, 1700]
        self.threshold2 = [2000, 2000]
        self.feedback_controller = feedback_controller

        self.segmenting_joints = {'bicep_curls': [['right_hip', 'right_shoulder', 'right_elbow', 'xz'],
                                                    ['left_hip', 'left_shoulder', 'left_elbow', 'xz'],
                                                    ['right_shoulder', 'right_elbow', 'right_wrist', 'xz'],
                                                    ['left_shoulder', 'left_elbow', 'left_wrist', 'xz']],
                                    'lateral_raises': [['right_hip', 'right_shoulder', 'right_elbow', 'xy'],
                                                    ['right_hip', 'right_shoulder', 'right_elbow', 'xz'],
                                                    ['left_hip', 'left_shoulder', 'left_elbow', 'xz'],
                                                    ['right_shoulder', 'right_elbow', 'right_wrist', 'xz'],
                                                    ['left_shoulder', 'left_elbow', 'left_wrist', 'xz']]}
        self.joint_groups = {'right_shoulder': [
                ['right_hip', 'right_shoulder', 'right_elbow', 'xy'],
                ['right_hip', 'right_shoulder', 'right_elbow', 'yz'],
                ['right_hip', 'right_shoulder', 'right_elbow', 'xz']
            ],
            'left_shoulder': [
                ['left_hip', 'left_shoulder', 'left_elbow', 'xy'],
                ['left_hip', 'left_shoulder', 'left_elbow', 'yz'],
                ['left_hip', 'left_shoulder', 'left_elbow', 'xz']
            ],
            'right_elbow': [
                ['right_shoulder', 'right_elbow', 'right_wrist', 'xy'],
                ['right_shoulder', 'right_elbow', 'right_wrist', 'yz'],
                ['right_shoulder', 'right_elbow', 'right_wrist', 'xz']
            ],
            'left_elbow': [
                ['left_shoulder', 'left_elbow', 'left_wrist', 'xy'],
                ['left_shoulder', 'left_elbow', 'left_wrist', 'yz'],
                ['left_shoulder', 'left_elbow', 'left_wrist', 'xz']
            ]}
        
        #Set the variables from the file
        self.experts = {}
        self.expert_duration = {}
        self.labels = {}
        self.good_experts = {}

        self.all_exercises = ['bicep_curls', 'lateral_raises']
        for exercise_name in self.all_exercises:
            npzfile = np.load('src/quori_exercises/experts/{}_updated_experts.npz'.format(exercise_name), allow_pickle=True)

            self.experts[exercise_name] = npzfile['experts']
            self.expert_duration[exercise_name] = npzfile['expert_duration']
            self.labels[exercise_name] = npzfile['labels']

            self.good_experts[exercise_name] = np.array([ii for ii, label in enumerate(self.labels[exercise_name]) if 'Good' in label]).astype(int)

            # self.set_joint_groups(exercise_name)

        self.angles = {'right_shoulder': [], 'left_shoulder': [], 'right_elbow': [], 'left_elbow': []}
        self.performance = []
        self.peaks = []
        self.feedback = []
        self.times = []
        self.current_exercise = ''
        self.exercise_name_list = []

    def start_new_set(self, exercise_name):
        for joint_group in self.angles.keys():
            self.angles[joint_group].append(np.empty((0, len(self.joint_groups[joint_group]))))

        self.performance.append(np.empty((0, len(self.joint_groups[exercise_name]))))
        self.peaks.append([])
        self.feedback.append([])
        self.times.append([])
        self.current_exercise = exercise_name
        self.exercise_name_list.append(exercise_name)

    def find_peaks(self, index_to_search):
        peaks = []
        grads = []
        angles = []
        for joint_group in self.joint_groups:
            for angle_ind, angle in enumerate(self.joint_groups[joint_group]):
                grads.append(np.gradient(self.angles[joint_group][index_to_search,angle_ind]))
                angles.append(self.angles[joint_group][index_to_search,angle_ind])
                if angle in self.segmenting_joints[self.current_exercise]:
                    peaks.append(signal.find_peaks(grads[-1], height=1.5, distance=20, prominence=0.5)[0].astype('int'))
        peaks = np.sort(np.concatenate(peaks))

        # grads = np.zeros_like(angles)
        
        # for joint_ind in range(angles.shape[1]):
        #     grads[:, joint_ind] = np.gradient(angles[:,joint_ind])
        #     if joint_ind in self.segmenting_joints[self.current_exercise]:
        #         peaks.append(signal.find_peaks(grads[:, joint_ind], height=1.5, distance=20, prominence=0.5)[0].astype('int'))
        # peaks = np.sort(np.concatenate(peaks))
        return peaks, angles, grads

    def check_if_new_peak(self, angles, grads, peak_candidate, index_to_search):
        #Peaks in absolute indices
        #Grads, peak_candidates in relative units
        
        if (len(self.peaks[-1]) == 0 and index_to_search[peak_candidate] > 15) or (len(self.peaks[-1]) > 0 and self.peaks[-1][-1] + 15 < index_to_search[peak_candidate]):
            range_to_check = np.arange(np.max([peak_candidate-4, 0]), np.min([peak_candidate+4, grads.shape[0]])).astype('int')
            
            max_val = np.argmax(grads[range_to_check,:][:,self.segmenting_joints[self.current_exercise]],axis=0)
            max_val = np.mean(max_val).astype('int')

            grad_min = -5
            grad_max = 5

            actual_grad_max = np.max(grads[range_to_check][:, self.segmenting_joints[self.current_exercise]])
            actual_grad_min = np.min(grads[range_to_check][:, self.segmenting_joints[self.current_exercise]])
            if self.current_exercise == 'bicep_curls':
                actual_max = np.max(angles[:,self.segmenting_joints[self.current_exercise][[0, 3]]])
                actual_min = np.min(angles[:,self.segmenting_joints[self.current_exercise][[0, 3]]])
            else:
                actual_max = np.max(angles[:,self.segmenting_joints[self.current_exercise]])
                actual_min = np.min(angles[:,self.segmenting_joints[self.current_exercise]])

            actual_max_loc = np.where(angles[:,self.segmenting_joints[self.current_exercise]] == actual_max)[0][0]
            actual_min_loc = np.where(angles[:,self.segmenting_joints[self.current_exercise]] == actual_min)[0][0]

            # print(index_to_search[range_to_check[max_val]], 'Grad Max:', actual_grad_max, 'Grad Min:', actual_grad_min, 'Max Loc:', actual_max_loc, 'Min Loc:', actual_min_loc, 'Actual Max:', actual_max, 'Actual Min:', actual_min)
            if (actual_grad_max > grad_max \
                or actual_grad_min < grad_min) \
                    and actual_max_loc > actual_min_loc:
                
                if (self.current_exercise == 'bicep_curls' and actual_min < 50 and actual_max > 100) or (self.current_exercise == 'lateral_raises' and actual_max > 100 and actual_min < 50):
                    # print('added')
                    return range_to_check[max_val]
            
        return False

    # def set_joint_groups(self, exercise_name):
    #     groups = {}
    #     for joint_ind, joint in enumerate(self.joints[exercise_name]):
    #         if joint[-1] in groups.keys():
    #             groups[joint[-1]].append(joint_ind)
    #         else:
    #             groups[joint[-1]] = [joint_ind]
    #     self.joint_groups[exercise_name] = groups

    #     joint_to_groups = np.zeros((len(self.joints[exercise_name])))
    #     counter = 0
    #     for joint_group, joints in self.joint_groups[exercise_name].items():
    #         for joint in joints:
    #             joint_to_groups[joint] = counter
    #         counter += 1
        
    #     self.joint_to_groups[exercise_name] = np.array(joint_to_groups).astype(int)

    def calc_dist_worker(self, ind, series1, series2, q):
            q.put((ind, fastdtw(series1, series2, dist=euclidean)))

    def calc_dist(self, current_rep, joints):

        input_values = [self.experts[self.current_exercise][ii][:,joints] for ii in range(len(self.experts[self.current_exercise]))]
        qout = multiprocessing.Queue()
        processes = [multiprocessing.Process(target=self.calc_dist_worker, args=(ind, current_rep, val, qout))
                for ind, val in enumerate(input_values)]
        
        for p in processes:
            p.start()

        for p in processes:
            p.join()

        unsorted_result = [qout.get() for p in processes]
        result = [t[1][0] for t in sorted(unsorted_result)]

        return result

    def evaluate_rep(self, start, stop, rep_duration):

        corrections = {}
        eval_list = {}

        for joint_group in self.joint_groups:
            angles = self.angles[joint_group][start:stop,:]
            expert_distances = self.calc_dist(angles, self.joint_groups[joint_group])

            threshold1 = self.threshold1[self.all_exercises.index(self.current_exercise)]
            threshold2 = self.threshold2[self.all_exercises.index(self.current_exercise)]

            good_distances = [expert_distances[ii] for ii in self.good_experts[self.current_exercise]]
            
            # for joint_group, joints in self.joint_groups[self.current_exercise].items():
                
            #     #Get expert distances per group
            #     expert_distances = self.calc_dist(current_rep[:, joints], joints)


            #     #Get closest good expert
            #     if self.current_exercise == 'bicep_curls':
            #         threshold1 = self.threshold1[0]
            #         threshold2 = self.threshold2[0]
            #     else:
            #         threshold1 = self.threshold1[1]
            #         threshold2 = self.threshold2[1]

            

            closest_expert = np.argmin(expert_distances)
            best_distance = np.min(expert_distances)
            expert_label = self.labels[self.current_exercise][closest_expert]
            self.feedback_controller.logger.info('Good expert min {} All expert min {}'.format(np.min(good_distances), np.min(expert_distances)))


            if best_distance < threshold1:
                if expert_label == 'Good':
                    eval_list[joint_group] = 1
                else:
                    eval_list[joint_group] = -1
                correction = expert_label
            elif best_distance < threshold2:
                if expert_label == 'Good':
                    correction = 'ok'
                    eval_list[joint_group] = 0
                else:
                    correction = 'bad'
                    eval_list[joint_group] = -1
            else:
                correction = 'bad'
                eval_list[joint_group] = -1
            
            correction += ' {}'.format(joint_group)
            corrections[joint_group] = correction
        
        if rep_duration < np.mean(self.expert_duration[self.current_exercise]) - 3:
            speed = 'fast'
        elif rep_duration > np.mean(self.expert_duration[self.current_exercise]) + 3 and rep_duration < 7:
            speed = 'slow'
        else:
            speed = 'good'
        
        self.feedback_controller.logger.info('Actual Duration {}, Average Expert Duration {}'.format(rep_duration, np.mean(self.expert_duration[self.current_exercise])))

        feedback = {'speed': speed, 'correction': corrections, 'evaluation': eval_list}

        self.feedback[-1].append(feedback)
        self.performance[-1] = np.vstack((self.performance[-1], feedback['evaluation']))
        
        self.feedback_controller.logger.info(feedback)
        self.feedback_controller.react(self.feedback[-1], self.current_exercise)

        return feedback

    def pose_callback(self, angle_message):

        if len(self.angles) == 0 or len(self.peaks) == 0:
            return

        if not self.flag:
           
                if self.angles[-1].shape[0] > 10 and len(self.peaks[-1]) > 0 and self.peaks[-1][-1] + 20 < self.angles[-1].shape[0]:
                    #Add last point
                    self.peaks[-1].append(self.angles[-1].shape[0]-1)

                    #Evaluate rep
                    current_rep = self.angles[-1][self.peaks[-1][-2]:self.peaks[-1][-1],:]
                    rep_duration = (self.times[-1][self.peaks[-1][-2]] - self.times[-1][self.peaks[-1][-1]]).total_seconds()
                    self.evaluate_rep(current_rep, rep_duration)

                return

        #Read angle from message
        self.angles['right_shoulder'][-1] = np.vstack(self.angles['right_shoulder'][-1], np.array(angle_message.right_shoulder.data))
        self.angles['left_shoulder'][-1] = np.vstack(self.angles['left_shoulder'][-1], np.array(angle_message.right_shoulder.data))
        self.angles['right_elbow'][-1] = np.vstack(self.angles['right_elbow'][-1], np.array(angle_message.right_shoulder.data))
        self.angles['left_elbow'][-1] = np.vstack(self.angles['left_elbow'][-1], np.array(angle_message.right_shoulder.data))

        #Get time
        time = datetime.now(timezone('EST'))
        self.times[-1].append(time)

        #Look for new peaks
        if self.angles['right_shoulder'][-1].shape[0] % 10 == 0 and self.angles['right_shoulder'][-1].shape[0] > 15:

            index_to_search = np.arange(np.max([0,self.angles['right_shoulder'][-1].shape[0]-500]), self.angles['right_shoulder'][-1].shape[0]).astype('int')
            
            peak_candidates, current_angles, grads  = self.find_peaks(index_to_search)
                
            #Get actual list of peaks
            for peak_candidate in peak_candidates:
                res = self.check_if_new_peak(current_angles, grads, peak_candidate, index_to_search)
                if res:
                    self.peaks[-1].append(index_to_search[res])
                    self.feedback_controller.logger.info('Current peak {}'.format(self.peaks[-1][-1]))

                    #Evaluate new rep
                    if len(self.peaks[-1]) > 1:
                        rep_duration = (self.times[-1][self.peaks[-1][-1]] - self.times[-1][self.peaks[-1][-2]]).total_seconds()
                        self.evaluate_rep(self.peaks[-1][-2], self.peaks[-1][-1], rep_duration)
                                          
    def reeval(self):
        for index, angle in enumerate(self.angles):
            #Look for new peaks
            if index > 15:
                index_to_search = np.arange(0, index).astype('int')
                
                peak_candidates, grads  = self.find_peaks(self.angles[index_to_search,:])
  
                #Get actual list of peaks
                for peak_candidate in peak_candidates:
                    res = self.check_if_new_peak(grads, peak_candidate, index_to_search)
                    if res:
                        self.peaks.append(index_to_search[res])

                        #Evaluate new rep
                        if len(self.peaks) > 1:
                            current_rep = self.angles[self.peaks[-2]:self.peaks[-1],:]
                            rep_duration = (self.times[self.peaks[-1]] - self.times[self.peaks[-2]]).total_seconds()
                            feedback = self.evaluate_rep(current_rep, rep_duration)
                            self.feedback.append(feedback)
                            self.performance = np.vstack((self.performance, feedback['evaluation']))
            time.sleep(0.1)

    def plot_results(self):

        fig, ax = plt.subplots(self.angles.shape[1], sharex=True, sharey=True)
        
        for ii in range(self.angles.shape[1]):
            ax[ii].plot(self.angles[:,ii], 'k', linestyle=':')
            ax[ii].plot(np.gradient(self.angles[:,ii]), 'k')

            counter = 0
            for start, end in zip(self.peaks[:-1], self.peaks[1:]):
                if counter % 2 == 0:
                    style = '--'
                else:
                    style = '-'
                if counter < len(self.feedback):
                    correction = self.feedback[counter]['correction'][self.joint_to_groups[ii]]
                    if 'Good' in correction:
                        color = 'g'
                    elif 'ok' in correction:
                        color = 'y'
                    elif 'bad' in correction:
                        color = 'r'
                    elif 'low' in correction:
                        color = 'm'
                    elif 'high' in correction:
                        color = 'b'
                    else:
                        color = 'k' 

                    ax[ii].plot(np.arange(start, end), self.angles[start:end,ii], linestyle=style, color=color)
                

                counter += 1

            ax[ii].set_title('{}-{}-{}-{}-{}'.format(ii,self.joints[ii][0], self.joints[ii][1], self.joints[ii][2], self.joints[ii][3]), fontsize = 8)
        plt.show()

