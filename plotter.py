import csv
import argparse
import time
import numpy as np
import matplotlib.pyplot as plt

def plotter(cfile, style, tail, period):

    factor = 1.5
  
    if style: 
        
        try:

            plt.style.use([style])

        except Exception as e:

            print plt.style.available
            raise e
    
    def get():
        pods = []
        users = []
        threads = []

        with open (cfile, 'rb') as csvfile:

            r = csv.reader(csvfile)

            for row in r:

                if len(row) == 3: 

                    pods += [row[0]]
                    users += [row[1]]
                    threads += [row[2]]

        pods = map(lambda x: float(x)*factor, pods)
        th_tens = [float(th)*factor/10 for th in threads]
        us_huns = [float(us)*factor/100 for us in users]
        x = [i for i in range(len(pods))]

        return x, pods, th_tens, us_huns

    if not tail:

        x, pods, th_tens, us_huns = get()
        plt.xlabel('Time Units')
        plt.ylabel('Quantity')
        plt.title('Cluster Size, Simulated Users, Threads Over Time')
        plt.plot(x, us_huns, label='Simulated Users (x100)')
        plt.plot(x, th_tens, label='Open Flask Threads (x10)')
        plt.plot(x, pods, label='Flask Pods in Cluster')
        plt.show()
        plt.legend(loc=0)

    else:

        plt.ion()
        fig = plt.figure()
        ax = fig.add_subplot(1,1,1)
        ax.set_xlabel('Time Units')
        ax.set_ylabel('Quantity')
        ax.set_title('Cluster Size, Simulated Users, Threads Over Time')
        line1, = ax.plot([], [], label='Simulated Users (x100)')
        line2, = ax.plot([], [], label='Open Flask Threads (x10)')
        line3, = ax.plot([], [], label='Flask Pods in Cluster')

        ax.legend(loc=0)        

        counts = 20
        prev = 0
        while counts > 0:

            x, pods, th_tens, us_huns = get()
            line1.set_data(x, us_huns)
            line2.set_data(x, th_tens)
            line3.set_data(x, pods)

            ax.relim()
            ax.autoscale_view()
            plt.pause(period)

            if len(x) == prev:
                counts -= 1

            else:
                counts = 20
                prev = len(x)

if __name__ == "__main__":
    
    parser = argparse.ArgumentParser()

    parser.add_argument('file', help='path to csv file')
    parser.add_argument('--style', '-s', help='style', default=None)
    parser.add_argument('--tail', '-t', help='tail csv', action='store_true')
    parser.add_argument('--period', '-p', help='update time period', default=2.0, type=float)

    args = parser.parse_args()

    plotter(args.file, args.style, args.tail, args.period)

