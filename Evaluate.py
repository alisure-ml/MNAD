import os
import glob
import argparse
from utils import *
import torch.utils.data as data
from model.Reconstruction import *
from model.utils import DataLoader
from torch.autograd import Variable
from collections import OrderedDict
import torchvision.transforms as transforms


# AUC:  95.30846148292541 %


parser = argparse.ArgumentParser(description="MNAD")
parser.add_argument('--batch_size', type=int, default=4, help='batch size for training')
parser.add_argument('--test_batch_size', type=int, default=1, help='batch size for test')
parser.add_argument('--h', type=int, default=256, help='height of input images')
parser.add_argument('--w', type=int, default=256, help='width of input images')
parser.add_argument('--c', type=int, default=3, help='channel of input images')
parser.add_argument('--method', type=str, default='pred', help='The target task for anoamly detection')
parser.add_argument('--t_length', type=int, default=5, help='length of the frame sequences')
parser.add_argument('--fdim', type=int, default=512, help='channel dimension of the features')
parser.add_argument('--mdim', type=int, default=512, help='channel dimension of the memory items')
parser.add_argument('--msize', type=int, default=10, help='number of the memory items')
parser.add_argument('--alpha', type=float, default=0.6, help='weight for the anomality score')
parser.add_argument('--th', type=float, default=0.01, help='threshold for test updating')
parser.add_argument('--num_workers', type=int, default=2, help='number of workers for the train loader')
parser.add_argument('--num_workers_test', type=int, default=1, help='number of workers for the test loader')
parser.add_argument('--dataset_path', type=str, default='./data', help='directory of data')

# parser.add_argument('--dataset_type', type=str, default='ped2', help='type of dataset: ped2, avenue, shanghai')
# parser.add_argument('--model_dir', type=str, help='directory of model',
#                     default="./pretrained_model/Ped2_prediction/Ped2_prediction_model.pth")
# parser.add_argument('--m_items_dir', type=str, help='directory of memory',
#                     default="./pretrained_model/Ped2_prediction/Ped2_prediction_keys.pt")

parser.add_argument('--dataset_type', type=str, default='ped2', help='type of dataset: ped2, avenue, shanghai')
parser.add_argument('--model_dir', type=str, help='directory of model',
                    default="./exp/ped2/pred/log/ped2_2/model_60.pth")
parser.add_argument('--m_items_dir', type=str, help='directory of memory',
                    default="./exp/ped2/pred/log/ped2_2/keys_60.pt")

# parser.add_argument('--dataset_type', type=str, default='avenue', help='type of dataset: ped2, avenue, shanghai')
# parser.add_argument('--model_dir', type=str, help='directory of model',
#                     default="./pretrained_model/Avenue_prediction/Avenue_prediction_model.pth")
# parser.add_argument('--m_items_dir', type=str, help='directory of memory',
#                     default="./pretrained_model/Avenue_prediction/Avenue_prediction_keys.pt")

args = parser.parse_args()


os.environ["CUDA_DEVICE_ORDER"]="PCI_BUS_ID"
os.environ["CUDA_VISIBLE_DEVICES"]= "0"
torch.backends.cudnn.enabled = True # make sure to use cudnn for computational performance


# Loading dataset
test_folder = args.dataset_path+"/"+args.dataset_type+"/testing/frames"
test_dataset = DataLoader(test_folder, transforms.Compose([transforms.ToTensor()]),
                          resize_height=args.h, resize_width=args.w, time_step=args.t_length-1)
test_size = len(test_dataset)
test_batch = data.DataLoader(test_dataset, batch_size = args.test_batch_size, 
                             shuffle=False, num_workers=args.num_workers_test, drop_last=False)


loss_func_mse = nn.MSELoss(reduction='none')

# Loading the trained model
model = torch.load(args.model_dir)
model.cuda()
m_items = torch.load(args.m_items_dir)
labels = np.load('./data/frame_labels_'+args.dataset_type+'.npy')

videos = OrderedDict()
videos_list = sorted(glob.glob(os.path.join(test_folder, '*')))
for video in videos_list:
    video_name = video.split('/')[-1]
    videos[video_name] = {}
    videos[video_name]['path'] = video
    videos[video_name]['frame'] = glob.glob(os.path.join(video, '*.jpg'))
    videos[video_name]['frame'].sort()
    videos[video_name]['length'] = len(videos[video_name]['frame'])
    pass

labels_list = []
label_length = 0
psnr_list = {}
feature_distance_list = {}


print('Evaluation of', args.dataset_type)

# Setting for video anomaly detection
for video in sorted(videos_list):
    video_name = video.split('/')[-1]
    if args.method == 'pred':
        labels_list = np.append(labels_list, labels[0][4+label_length:videos[video_name]['length']+label_length])
    else:
        labels_list = np.append(labels_list, labels[0][label_length:videos[video_name]['length']+label_length])
    label_length += videos[video_name]['length']
    psnr_list[video_name] = []
    feature_distance_list[video_name] = []
    pass


label_length = 0
video_num = 0
label_length += videos[videos_list[video_num].split('/')[-1]]['length']


model.eval()
m_items_test = m_items.clone()
for k,(imgs) in enumerate(test_batch):
    if args.method == 'pred':
        if k == label_length-4*(video_num+1):
            video_num += 1
            label_length += videos[videos_list[video_num].split('/')[-1]]['length']
    else:
        if k == label_length:
            video_num += 1
            label_length += videos[videos_list[video_num].split('/')[-1]]['length']
        pass

    imgs = Variable(imgs).cuda()
    
    if args.method == 'pred':
        (outputs, feas, updated_feas, m_items_test, softmax_score_query, softmax_score_memory,
         _, _, _, compactness_loss) = model.forward(imgs[:,0:3*4], m_items_test, False)
        mse_imgs = torch.mean(loss_func_mse((outputs[0]+1)/2, (imgs[0,3*4:]+1)/2)).item()
        mse_feas = compactness_loss.item()
        # Calculating the threshold for updating at the test time
        point_sc = point_score(outputs, imgs[:,3*4:])
    else:
        (outputs, feas, updated_feas, m_items_test, softmax_score_query,
         softmax_score_memory, compactness_loss) = model.forward(imgs, m_items_test, False)
        mse_imgs = torch.mean(loss_func_mse((outputs[0]+1)/2, (imgs[0]+1)/2)).item()
        mse_feas = compactness_loss.item()
        # Calculating the threshold for updating at the test time
        point_sc = point_score(outputs, imgs)
        pass

    if  point_sc < args.th:
        query = F.normalize(feas, dim=1)
        query = query.permute(0,2,3,1) # b X h X w X d
        m_items_test = model.memory.update(query, m_items_test, False)
        pass

    psnr_list[videos_list[video_num].split('/')[-1]].append(psnr(mse_imgs))
    feature_distance_list[videos_list[video_num].split('/')[-1]].append(mse_feas)
    pass


# Measuring the abnormality score and the AUC
anomaly_score_total_list = []
for video in sorted(videos_list):
    video_name = video.split('/')[-1]
    anomaly_score_total_list += score_sum(anomaly_score_list(psnr_list[video_name]),
                                          anomaly_score_list_inv(feature_distance_list[video_name]), args.alpha)
    pass

anomaly_score_total_list = np.asarray(anomaly_score_total_list)
accuracy = AUC(anomaly_score_total_list, np.expand_dims(1-labels_list, 0))

print('The result of ', args.dataset_type)
print('AUC: ', accuracy*100, '%')

